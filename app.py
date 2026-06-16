import os, random, string
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import (db, bcrypt, Usuario, Convocatoria, PuestoConvocatoria, Postulante,
                    Induccion, PreguntaInduccion, AvanceInduccion, DeclaracionSalud,
                    DiaTopico, BloqueTopico, CitaTopico, HistorialEstado)
from seed import seed_db

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'agrotalent-secret-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///agrotalent.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
bcrypt.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Debes iniciar sesión para continuar.'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(uid):
    return db.session.get(Usuario, int(uid))


@app.template_filter('hora_ampm')
def hora_ampm(valor):
    try:
        from datetime import datetime as dt
        t = dt.strptime(str(valor), '%H:%M')
        return t.strftime('%I:%M %p')
    except Exception:
        return valor


# ── helpers ─────────────────────────────────────────────────────────────────

def registrar_historial(p, estado_nuevo, desc=''):
    db.session.add(HistorialEstado(postulante_id=p.id,
                                   estado_anterior=p.estado_proceso,
                                   estado_nuevo=estado_nuevo, descripcion=desc))
    p.estado_proceso = estado_nuevo


def generar_otp():
    return ''.join(random.choices(string.digits, k=6))


def mensaje_presentacion(conv):
    """Mensaje de confirmación de vacante: indica fecha, hora y lugar
    de presentación tomados de la convocatoria activa."""
    if not conv:
        return '¡Felicitaciones! Fuiste seleccionado. Pronto te informaremos fecha, hora y lugar de presentación.'
    fecha = conv.fecha_presentacion.strftime('%d/%m/%Y') if conv.fecha_presentacion else '—'
    hora = hora_ampm(conv.hora_presentacion) if conv.hora_presentacion else '—'
    lugar = conv.lugar_presentacion or '—'
    return f'¡Felicitaciones! Fuiste seleccionado. Preséntate el {fecha} a las {hora} en {lugar}.'


def asegurar_codigo_constancia(p):
    """Genera y persiste un código alfanumérico único para la Constancia de
    Habilitación si el postulante aún no tiene uno."""
    if p.codigo_constancia:
        return p.codigo_constancia
    letras = string.ascii_uppercase
    while True:
        candidato = 'CH-' + ''.join(random.choices(letras + string.digits, k=6))
        if not Postulante.query.filter_by(codigo_constancia=candidato).first():
            p.codigo_constancia = candidato
            return candidato


def estado_constancia(p):
    """Mapea el estado interno del proceso al estado mostrado en la
    Constancia de Habilitación."""
    if p.estado_proceso in ('seleccionado', 'incorporado'):
        return 'habilitado'
    if p.estado_proceso == 'cita_programada':
        return 'evaluacion'
    if p.estado_proceso == 'lista_espera':
        return 'espera'
    return 'pendiente'


def rol_requerido(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.rol not in roles:
                flash('Acceso restringido.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def convocatoria_activa():
    return Convocatoria.query.filter_by(activa=True).first()


# ── INDEX ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ── AUTH ─────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_redirect'))
    if request.method == 'POST':
        tipo = request.form.get('tipo_login', 'postulante')
        password = request.form.get('password', '').strip()

        if tipo == 'postulante':
            dni = request.form.get('dni', '').strip()
            usuario = Usuario.query.filter_by(dni=dni, rol='postulante').first()
        else:
            correo = request.form.get('correo', '').strip()
            usuario = Usuario.query.filter(
                Usuario.correo == correo,
                Usuario.rol.in_(['rrhh', 'medico'])
            ).first()

        if not usuario:
            flash('Credenciales incorrectas.', 'danger')
            return render_template('auth/login.html')

        # Bloqueo temporal
        if usuario.bloqueado_hasta and usuario.bloqueado_hasta > datetime.utcnow():
            mins = int((usuario.bloqueado_hasta - datetime.utcnow()).total_seconds() // 60) + 1
            flash(f'Cuenta bloqueada. Intenta en {mins} minuto(s).', 'danger')
            return render_template('auth/login.html')

        if not usuario.check_password(password):
            usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
            if usuario.intentos_fallidos >= 5:
                usuario.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=15)
                usuario.intentos_fallidos = 0
                flash('5 intentos fallidos. Cuenta bloqueada 15 minutos.', 'danger')
            else:
                flash(f'Credenciales incorrectas. Intento {usuario.intentos_fallidos}/5.', 'danger')
            db.session.commit()
            return render_template('auth/login.html')

        if not usuario.verificado:
            flash('Tu cuenta no está verificada. Revisa el código enviado.', 'warning')
            return redirect(url_for('verificar_otp', dni=usuario.dni))

        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        db.session.commit()
        login_user(usuario)
        return redirect(url_for('dashboard_redirect'))

    return render_template('auth/login.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        dni = request.form.get('dni', '').strip()
        nombres = request.form.get('nombres', '').strip()
        apellidos = request.form.get('apellidos', '').strip()
        celular = request.form.get('celular', '').strip()
        password = request.form.get('password', '').strip()
        confirmar = request.form.get('confirmar', '').strip()

        if len(dni) != 8 or not dni.isdigit():
            flash('El DNI debe tener 8 dígitos.', 'danger')
            return render_template('auth/registro.html')
        if Usuario.query.filter_by(dni=dni).first():
            flash('Este DNI ya está registrado.', 'danger')
            return render_template('auth/registro.html')
        if password != confirmar:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('auth/registro.html')
        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            return render_template('auth/registro.html')

        otp = generar_otp()
        usuario = Usuario(dni=dni, nombres=nombres, apellidos=apellidos,
                          celular=celular, rol='postulante', verificado=False,
                          otp_code=otp,
                          otp_expira=datetime.utcnow() + timedelta(minutes=5))
        usuario.set_password(password)
        db.session.add(usuario)
        db.session.flush()
        conv_activa = convocatoria_activa()
        db.session.add(Postulante(
            usuario_id=usuario.id,
            estado_proceso='registrado',
            convocatoria_id=conv_activa.id if conv_activa else None
        ))
        db.session.commit()
        # En producción: enviar OTP por SMS. Aquí lo mostramos en pantalla.
        flash(f'Código de verificación generado.', 'info')
        return redirect(url_for('verificar_otp', dni=dni))

    return render_template('auth/registro.html')


@app.route('/verificar/<dni>', methods=['GET', 'POST'])
def verificar_otp(dni):
    usuario = Usuario.query.filter_by(dni=dni).first_or_404()
    if usuario.verificado:
        return redirect(url_for('login'))
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'reenviar':
            otp = generar_otp()
            usuario.otp_code = otp
            usuario.otp_expira = datetime.utcnow() + timedelta(minutes=5)
            db.session.commit()
            flash('Nuevo código generado.', 'info')
            return redirect(url_for('verificar_otp', dni=dni))

        codigo = request.form.get('codigo', '').strip()
        if not usuario.otp_expira or datetime.utcnow() > usuario.otp_expira:
            flash('El código expiró. Solicita uno nuevo.', 'danger')
            return render_template('auth/verificar_otp.html', usuario=usuario)
        if codigo != usuario.otp_code:
            flash('Código incorrecto.', 'danger')
            return render_template('auth/verificar_otp.html', usuario=usuario)

        usuario.verificado = True
        usuario.otp_code = None
        usuario.otp_expira = None
        db.session.commit()
        login_user(usuario)
        flash('¡Cuenta verificada! Completa tus datos personales.', 'success')
        return redirect(url_for('postulante_datos'))

    return render_template('auth/verificar_otp.html', usuario=usuario)


@app.route('/dashboard')
@login_required
def dashboard_redirect():
    r = current_user.rol
    if r == 'rrhh':   return redirect(url_for('rrhh_dashboard'))
    if r == 'medico': return redirect(url_for('medico_dashboard'))
    return redirect(url_for('postulante_dashboard'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ── POSTULANTE ───────────────────────────────────────────────────────────────

@app.route('/postulante/dashboard')
@login_required
@rol_requerido('postulante')
def postulante_dashboard():
    p = current_user.postulante
    inducciones = Induccion.query.order_by(Induccion.orden).all()
    avances = {a.induccion_id: a for a in p.inducciones}
    conv = convocatoria_activa()
    return render_template('postulante/dashboard.html',
                           postulante=p, inducciones=inducciones,
                           avances=avances, conv=conv)


@app.route('/postulante/constancia')
@login_required
@rol_requerido('postulante')
def postulante_constancia():
    p = current_user.postulante
    conv = convocatoria_activa()
    if estado_constancia(p) == 'habilitado' and not p.codigo_constancia:
        asegurar_codigo_constancia(p)
        db.session.commit()
    return render_template('postulante/constancia.html',
                           postulante=p, conv=conv, estado=estado_constancia(p))


@app.route('/postulante/constancia/imprimir')
@login_required
@rol_requerido('postulante')
def postulante_constancia_imprimir():
    p = current_user.postulante
    conv = convocatoria_activa()
    if estado_constancia(p) == 'habilitado' and not p.codigo_constancia:
        asegurar_codigo_constancia(p)
        db.session.commit()
    return render_template('postulante/constancia_imprimir.html',
                           postulante=p, conv=conv, estado=estado_constancia(p),
                           now_str=datetime.utcnow().strftime('%d/%m/%Y'))


DISTRITOS = ['Piura','Castilla','Catacaos','Cura Mori','El Tallán','La Arena',
             'La Unión','Las Lomas','Tambogrande','Veintiseis de Octubre']
PUESTOS   = ['Siembra','Guiado','Poda','Desbrote','Acomodo','Desoje','Ajuste','Descole','Raleo','Cosecha']
GRADOS    = ['Sin instrucción','Primaria incompleta','Primaria completa',
             'Secundaria incompleta','Secundaria completa','Técnico','Universitario']


@app.route('/postulante/datos', methods=['GET', 'POST'])
@login_required
@rol_requerido('postulante')
def postulante_datos():
    p = current_user.postulante
    conv = convocatoria_activa()
    conv = convocatoria_activa()
    puestos_conv = [pc.nombre_puesto for pc in conv.puestos if pc.vacantes_disponibles > 0] if conv else []

    def render_form():
        return render_template('postulante/datos.html', postulante=p,
                               distritos=DISTRITOS, puestos=puestos_conv, grados=GRADOS)

    if request.method == 'POST':
        fecha_str = request.form.get('fecha_nacimiento', '')
        try:
            fn = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Fecha de nacimiento inválida.', 'danger')
            return render_form()
        hoy = date.today()
        edad = hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
        if edad < 18:
            flash('Debes ser mayor de 18 años para postular.', 'danger')
            return render_form()
        # guardar nombres/apellidos (editables)
        current_user.nombres   = request.form.get('nombres', '').strip()
        current_user.apellidos = request.form.get('apellidos', '').strip()
        p.fecha_nacimiento = fn
        p.sexo = request.form.get('sexo', '')
        p.grado_instruccion = request.form.get('grado_instruccion', '')
        p.distrito = request.form.get('distrito', '')
        p.puesto = request.form.get('puesto', '')
        p.es_extrabajador = request.form.get('es_extrabajador') == 'si'
        p.datos_completos = True
        if p.estado_proceso == 'registrado':
            registrar_historial(p, 'en_proceso', 'Datos personales completados')
        db.session.commit()
        flash('Datos guardados correctamente.', 'success')
        return redirect(url_for('postulante_dashboard'))
    return render_form()


@app.route('/postulante/inducciones')
@login_required
@rol_requerido('postulante')
def postulante_inducciones():
    p = current_user.postulante
    if not p.datos_completos:
        flash('Primero completa tus datos personales.', 'warning')
        return redirect(url_for('postulante_datos'))
    inducciones = Induccion.query.order_by(Induccion.orden).all()
    avances = {a.induccion_id: a for a in p.inducciones}
    return render_template('postulante/inducciones.html',
                           postulante=p, inducciones=inducciones, avances=avances)


@app.route('/postulante/induccion/<int:ind_id>', methods=['GET', 'POST'])
@login_required
@rol_requerido('postulante')
def postulante_induccion_detalle(ind_id):
    p = current_user.postulante
    induccion = Induccion.query.get_or_404(ind_id)
    avances = {a.induccion_id: a for a in p.inducciones}

    if induccion.orden > 1:
        ind_ant = Induccion.query.filter_by(orden=induccion.orden - 1).first()
        av_ant = avances.get(ind_ant.id) if ind_ant else None
        if not av_ant or not av_ant.aprobado:
            flash('Debes aprobar la inducción anterior primero.', 'warning')
            return redirect(url_for('postulante_inducciones'))

    if request.method == 'POST':
        accion = request.form.get('accion')
        avance = avances.get(ind_id) or AvanceInduccion(postulante_id=p.id, induccion_id=ind_id)
        if not avances.get(ind_id):
            db.session.add(avance)

        if accion == 'video_completado':
            avance.video_completado = True
            db.session.commit()
            return redirect(url_for('postulante_induccion_detalle', ind_id=ind_id))

        # envío de cuestionario
        if not avance.video_completado:
            flash('Debes ver el video completo antes de responder.', 'warning')
            return redirect(url_for('postulante_induccion_detalle', ind_id=ind_id))

        todas_preguntas = induccion.preguntas
        correctas = sum(1 for preg in todas_preguntas
                        if request.form.get(f'preg_{preg.id}') == preg.respuesta_correcta
                        and request.form.get(f'preg_{preg.id}'))
        respondidas = sum(1 for preg in todas_preguntas if request.form.get(f'preg_{preg.id}'))
        aprobado = (respondidas > 0 and correctas == respondidas)

        avance.aprobado = aprobado
        avance.completado_en = datetime.utcnow()

        if aprobado:
            todas = Induccion.query.order_by(Induccion.orden).all()
            nuevos_avances = {a.induccion_id: a for a in p.inducciones}
            nuevos_avances[ind_id] = avance
            todas_aprobadas = all(nuevos_avances.get(i.id) and nuevos_avances[i.id].aprobado
                                  for i in todas)
            if todas_aprobadas:
                registrar_historial(p, 'en_proceso', 'Todas las inducciones aprobadas')
            elif p.estado_proceso == 'datos_completos':
                registrar_historial(p, 'en_proceso', f'{induccion.titulo} aprobada')
            db.session.commit()
            flash(f'¡Aprobaste! ({correctas}/{respondidas} correctas)', 'success')
        else:
            db.session.commit()
            flash(f'No aprobaste ({correctas}/{respondidas}). Debes responder todas correctamente. Inténtalo de nuevo.', 'danger')

        return redirect(url_for('postulante_inducciones'))

    avance_actual = avances.get(ind_id)
    import random as _random
    todas_pregs = list(induccion.preguntas)
    preguntas_aleatorias = _random.sample(todas_pregs, min(3, len(todas_pregs)))
    return render_template('postulante/induccion_detalle.html',
                           induccion=induccion, avance=avance_actual,
                           postulante=p, preguntas=preguntas_aleatorias)


@app.route('/postulante/declaracion-salud', methods=['GET', 'POST'])
@login_required
@rol_requerido('postulante')
def postulante_declaracion():
    p = current_user.postulante
    if p.estado_proceso not in ['en_proceso', 'declaracion_registrada']:
        flash('Debes completar todas las inducciones primero.', 'warning')
        return redirect(url_for('postulante_inducciones'))
    if p.declaracion:
        return render_template('postulante/declaracion.html',
                               postulante=p, declaracion=p.declaracion, ya_firmada=True)

    if request.method == 'POST':
        f = request.form
        def es_si(campo): return f.get(campo) == 'si'
        decl = DeclaracionSalud(
            postulante_id=p.id,
            mayor_65      = es_si('mayor_65'),
            hipertension  = es_si('hipertension'),
            diabetes      = es_si('diabetes'),
            cardiovascular= es_si('cardiovascular'),
            pulmonar_cronica= es_si('pulmonar_cronica'),
            cancer        = es_si('cancer'),
            asma          = es_si('asma'),
            enfisema      = es_si('enfisema'),
            epoc          = es_si('epoc'),
            obesidad      = es_si('obesidad'),
            gestacion     = es_si('gestacion'),
            sin_antecedentes= False,
        )
        db.session.add(decl)
        p.fecha_hora_declaracion = datetime.utcnow()
        registrar_historial(p, 'en_proceso', 'Declaración jurada firmada')

        conv = convocatoria_activa()
        puesto_conv = None
        if conv and p.puesto:
            puesto_conv = PuestoConvocatoria.query.filter_by(
                convocatoria_id=conv.id, nombre_puesto=p.puesto).first()

        hay_vacante = bool(puesto_conv and puesto_conv.vacantes_disponibles > 0)

        if decl.tiene_condicion:
            if hay_vacante:
                puesto_conv.vacantes_ocupadas += 1
                p.estado_vacante = 'reservada'
                db.session.commit()
                flash('Declaración registrada. Selecciona tu cita en tópico.', 'info')
                return redirect(url_for('postulante_cita_topico'))
            else:
                registrar_historial(p, 'lista_espera', 'Sin vacantes al declarar condición')
                db.session.commit()
                flash('Declaración registrada. Sin vacantes disponibles. Quedas en lista de espera.', 'warning')
                return redirect(url_for('postulante_dashboard'))
        else:
            if hay_vacante:
                puesto_conv.vacantes_ocupadas += 1
                p.estado_vacante = 'confirmada'
                p.fecha_hora_habilitacion = datetime.utcnow()
                registrar_historial(p, 'seleccionado', 'Vacante confirmada')
                asegurar_codigo_constancia(p)
                db.session.commit()
                flash(mensaje_presentacion(conv), 'success')
                return redirect(url_for('postulante_dashboard'))
            else:
                registrar_historial(p, 'lista_espera', 'Sin vacantes disponibles')
                db.session.commit()
                flash('Declaración registrada. Sin vacantes disponibles. Quedas en lista de espera.', 'warning')
                return redirect(url_for('postulante_dashboard'))

    return render_template('postulante/declaracion.html',
                           postulante=p, declaracion=None, ya_firmada=False)


@app.route('/postulante/cita-topico', methods=['GET', 'POST'])
@login_required
@rol_requerido('postulante')
def postulante_cita_topico():
    p = current_user.postulante
    conv = convocatoria_activa()
    dia = DiaTopico.query.filter_by(convocatoria_id=conv.id).first() if conv else None
    bloques_disponibles = [b for b in (dia.bloques if dia else []) if b.cupos_disponibles > 0]

    # Solo mostrar como ya_tiene_cita si la cita esta realmente confirmada
    if p.cita and p.estado_proceso == 'cita_programada':
        return render_template('postulante/cita_topico.html',
                               postulante=p, bloques=bloques_disponibles,
                               dia=dia, ya_tiene_cita=True,
                               confirmar=False, bloque_sel=None)

    if request.method == 'POST':
        accion = request.form.get('accion', 'seleccionar')
        bloque_id = request.form.get('bloque_id')
        bloque_obj = BloqueTopico.query.get(bloque_id) if bloque_id else None

        if accion == 'seleccionar':
            # Mostrar pantalla de confirmacion
            if not bloque_obj or bloque_obj.cupos_disponibles <= 0:
                flash('El bloque seleccionado no tiene cupos disponibles.', 'danger')
                return redirect(url_for('postulante_cita_topico'))
            return render_template('postulante/cita_topico.html',
                                   postulante=p, bloques=bloques_disponibles,
                                   dia=dia, ya_tiene_cita=False,
                                   confirmar=True, bloque_sel=bloque_obj)

        elif accion == 'confirmar':
            if not bloque_obj or bloque_obj.cupos_disponibles <= 0:
                flash('El bloque ya no tiene cupos disponibles.', 'danger')
                return redirect(url_for('postulante_cita_topico'))
            bloque_obj.cupos_ocupados += 1
            cita = CitaTopico(postulante_id=p.id, bloque_id=bloque_obj.id)
            db.session.add(cita)
            registrar_historial(p, 'cita_programada',
                                f'Cita {bloque_obj.dia.fecha} {bloque_obj.etiqueta}')
            db.session.commit()
            flash('Cita médica programada correctamente.', 'success')
            return redirect(url_for('postulante_dashboard'))

    return render_template('postulante/cita_topico.html',
                           postulante=p, bloques=bloques_disponibles,
                           dia=dia, ya_tiene_cita=False,
                           confirmar=False, bloque_sel=None)


# ── RR.HH. ───────────────────────────────────────────────────────────────────

@app.route('/rrhh/dashboard')
@login_required
@rol_requerido('rrhh')
def rrhh_dashboard():
    conv = convocatoria_activa()
    puestos = PuestoConvocatoria.query.filter_by(
        convocatoria_id=conv.id).all() if conv else []

    # indicadores operativos — solo postulantes de la convocatoria activa
    def q_conv(estado):
        q = Postulante.query.filter_by(estado_proceso=estado)
        if conv:
            q = q.filter_by(convocatoria_id=conv.id)
        return q.count()

    pendientes_topico  = q_conv('cita_programada')
    lista_espera       = q_conv('lista_espera')
    incorporados       = q_conv('incorporado')
    vacantes_liberadas = 0
    if conv:
        vacantes_liberadas = Postulante.query.filter(
            Postulante.convocatoria_id == conv.id,
            Postulante.estado_proceso.in_(['no_apto','no_se_presento'])
        ).count()
    puestos_filtrados = [p for p in puestos if p.vacantes_disponibles > 0]

    return render_template('rrhh/dashboard.html',
                           conv=conv, puestos=puestos_filtrados,
                           pendientes_topico=pendientes_topico,
                           vacantes_liberadas=vacantes_liberadas,
                           lista_espera=lista_espera,
                           incorporados=incorporados)


@app.route('/rrhh/postulantes')
@login_required
@rol_requerido('rrhh')
def rrhh_postulantes():
    estado  = request.args.get('estado', '')
    puesto  = request.args.get('puesto', '')
    cita_st = request.args.get('cita_estado', '')
    buscar  = request.args.get('buscar', '').strip()

    conv_activa = convocatoria_activa()
    todas_convs = Convocatoria.query.order_by(Convocatoria.fecha_apertura.desc()).all()
    conv_id_sel = request.args.get('conv_id', str(conv_activa.id) if conv_activa else '')
    conv_sel = Convocatoria.query.get(int(conv_id_sel)) if conv_id_sel else None

    q = Postulante.query.join(Usuario)
    if conv_sel:
        q = q.filter(Postulante.convocatoria_id == conv_sel.id)
    if estado:  q = q.filter(Postulante.estado_proceso == estado)
    if puesto:  q = q.filter(Postulante.puesto == puesto)
    if buscar:
        q = q.filter(db.or_(Usuario.dni.contains(buscar),
                             Usuario.nombres.contains(buscar),
                             Usuario.apellidos.contains(buscar)))
    postulantes = q.order_by(
        Postulante.es_extrabajador.desc(),
        Postulante.fecha_hora_declaracion.asc()
    ).all()

    puestos_conv = [p.nombre_puesto for p in conv_sel.puestos] if conv_sel else PUESTOS
    ESTADOS = ['registrado','en_proceso','cita_programada','seleccionado','lista_espera','incorporado','no_apto','no_se_presento']
    return render_template('rrhh/postulantes.html',
                           postulantes=postulantes, puestos=puestos_conv, estados=ESTADOS,
                           filtro_estado=estado, filtro_puesto=puesto, buscar=buscar,
                           todas_convs=todas_convs, conv_sel=conv_sel)


@app.route('/rrhh/postulante/<int:pid>')
@login_required
@rol_requerido('rrhh')
def rrhh_postulante_detalle(pid):
    p = Postulante.query.get_or_404(pid)
    return render_template('rrhh/postulante_detalle.html', postulante=p)


@app.route('/rrhh/postulante/<int:pid>/incorporar', methods=['POST'])
@login_required
@rol_requerido('rrhh')
def rrhh_incorporar(pid):
    p = Postulante.query.get_or_404(pid)
    if p.validado_en_fundo:
        registrar_historial(p, 'incorporado', f'Incorporado por {current_user.nombres}')
        db.session.commit()
        flash(f'{p.nombres} {p.apellidos} incorporado.', 'success')
    else:
        flash('El DNI del postulante no ha sido validado en el fundo aún.', 'warning')
    return redirect(url_for('rrhh_postulante_detalle', pid=pid))


@app.route('/rrhh/convocatoria', methods=['GET', 'POST'])
@login_required
@rol_requerido('rrhh')
def rrhh_convocatoria():
    conv = convocatoria_activa()
    if request.method == 'POST':
        accion = request.form.get('accion')

        if accion == 'cerrar' and conv:
            conv.activa = False
            conv.cerrada_manualmente = True
            db.session.commit()
            flash('Convocatoria cerrada manualmente.', 'success')
            return redirect(url_for('rrhh_convocatoria'))

        TODOS_PUESTOS = ['Siembra','Guiado','Poda','Desbrote','Acomodo','Desoje','Ajuste','Descole','Raleo','Cosecha']

        if not current_user.es_jefe and accion in ('editar', 'crear', 'cerrar'):
            flash('Solo el jefe de RR.HH. puede modificar la convocatoria.', 'danger')
            return redirect(url_for('rrhh_convocatoria'))
        if accion == 'editar' and conv:
            try:
                conv.nombre = request.form.get('nombre','').strip()
                conv.fecha_apertura = datetime.strptime(request.form.get('fecha_apertura',''), '%Y-%m-%dT%H:%M')
                conv.fecha_cierre = datetime.strptime(request.form.get('fecha_cierre',''), '%Y-%m-%dT%H:%M')
                conv.fecha_presentacion = datetime.strptime(request.form.get('fecha_presentacion',''), '%Y-%m-%d').date()
                conv.hora_presentacion = request.form.get('hora_presentacion','').strip()
                for nombre in TODOS_PUESTOS:
                    vacantes = int(request.form.get(f'vacantes_{nombre}', 0) or 0)
                    puesto = next((p for p in conv.puestos if p.nombre_puesto == nombre), None)
                    if puesto:
                        puesto.vacantes_total = vacantes
                    elif vacantes > 0:
                        db.session.add(PuestoConvocatoria(convocatoria_id=conv.id, nombre_puesto=nombre, vacantes_total=vacantes))
                db.session.commit()
                flash('Convocatoria actualizada correctamente.', 'success')
            except ValueError:
                flash('Fechas inválidas.', 'danger')
            return redirect(url_for('rrhh_convocatoria'))

        if accion == 'crear':
            if conv:
                flash('Ya existe una convocatoria activa. Ciérrala antes de crear una nueva.', 'danger')
                return redirect(url_for('rrhh_convocatoria'))
            try:
                f_apertura = datetime.strptime(request.form.get('fecha_apertura',''), '%Y-%m-%dT%H:%M')
                f_cierre   = datetime.strptime(request.form.get('fecha_cierre',''), '%Y-%m-%dT%H:%M')
                f_presentacion = datetime.strptime(request.form.get('fecha_presentacion',''), '%Y-%m-%d').date()
            except ValueError:
                flash('Fechas inválidas.', 'danger')
                return redirect(url_for('rrhh_convocatoria'))
            if f_cierre <= f_apertura:
                flash('La fecha de cierre debe ser posterior a la apertura.', 'danger')
                return redirect(url_for('rrhh_convocatoria'))
            nueva = Convocatoria(
                nombre=request.form.get('nombre','').strip(),
                fecha_apertura=f_apertura, fecha_cierre=f_cierre,
                fecha_presentacion=f_presentacion,
                hora_presentacion=request.form.get('hora_presentacion','').strip(),
                lugar_presentacion='Fundo de la Empresa Agroindustrial — Km 12 Carretera Piura-Chulucanas',
                activa=True
            )
            db.session.add(nueva)
            db.session.flush()
            for nombre in TODOS_PUESTOS:
                vacantes = int(request.form.get(f'vacantes_{nombre}', 0) or 0)
                if vacantes > 0:
                    db.session.add(PuestoConvocatoria(convocatoria_id=nueva.id, nombre_puesto=nombre, vacantes_total=vacantes))
            db.session.commit()
            flash('Convocatoria creada.', 'success')
            return redirect(url_for('rrhh_convocatoria'))

    historial = Convocatoria.query.order_by(Convocatoria.creado_en.desc()).all()
    return render_template('rrhh/convocatoria.html',
                           conv=conv, historial=historial, puestos_default=PUESTOS)


@app.route('/rrhh/topico', methods=['GET', 'POST'])
@login_required
@rol_requerido('rrhh')
def rrhh_topico():
    conv = convocatoria_activa()
    dia = DiaTopico.query.filter_by(convocatoria_id=conv.id).first() if conv else None

    if request.method == 'POST' and conv:
        if not current_user.es_jefe:
            flash('Solo el jefe de RR.HH. puede configurar los bloques de tópico.', 'danger')
            return redirect(url_for('rrhh_topico'))
        accion = request.form.get('accion', 'agregar_bloque')

        if accion == 'agregar_bloque':
            if not dia:
                # Check if dia already exists for this convocatoria (avoid unique conflict)
                dia = DiaTopico.query.filter_by(
                    convocatoria_id=conv.id, fecha=conv.fecha_presentacion).first()
                if not dia:
                    dia = DiaTopico(convocatoria_id=conv.id, fecha=conv.fecha_presentacion)
                    db.session.add(dia)
                    db.session.flush()
            # Determine next letter
            letras = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
            usadas = [b.nombre for b in BloqueTopico.query.filter_by(dia_id=dia.id).all()]
            siguiente = next((l for l in letras if l not in usadas), None)
            if not siguiente:
                flash('Maximo de bloques alcanzado.', 'danger')
                return redirect(url_for('rrhh_topico'))
            hora_inicio = request.form.get('hora_inicio', '').strip()
            hora_fin = request.form.get('hora_fin', '').strip()
            cupos = int(request.form.get('cupos', 0) or 0)
            if not hora_inicio or not hora_fin or cupos <= 0:
                flash('Completa todos los campos del bloque.', 'danger')
                return redirect(url_for('rrhh_topico'))
            db.session.add(BloqueTopico(
                dia_id=dia.id, nombre=siguiente,
                hora_inicio=hora_inicio, hora_fin=hora_fin, cupos_total=cupos))
            db.session.commit()
            flash('Bloque ' + siguiente + ' agregado.', 'success')

        elif accion == 'eliminar_bloque':
            bloque_id = int(request.form.get('bloque_id', 0))
            bloque = BloqueTopico.query.get(bloque_id)
            if bloque:
                if bloque.cupos_ocupados > 0:
                    flash('No se puede eliminar: tiene citas asignadas.', 'danger')
                else:
                    db.session.delete(bloque)
                    db.session.commit()
                    flash('Bloque eliminado.', 'success')

        elif accion == 'editar_bloque':
            bloque_id = int(request.form.get('bloque_id', 0))
            bloque = BloqueTopico.query.get(bloque_id)
            if bloque:
                bloque.hora_inicio = request.form.get('hora_inicio', bloque.hora_inicio)
                bloque.hora_fin = request.form.get('hora_fin', bloque.hora_fin)
                bloque.cupos_total = int(request.form.get('cupos', bloque.cupos_total) or bloque.cupos_total)
                db.session.commit()
                flash('Bloque actualizado.', 'success')

        return redirect(url_for('rrhh_topico'))

    bloques = list(BloqueTopico.query.filter_by(dia_id=dia.id).order_by(BloqueTopico.nombre).all()) if dia else []
    letras = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    usadas = [b.nombre for b in bloques]
    siguiente_letra = next((l for l in letras if l not in usadas), None)
    return render_template('rrhh/topico_horarios.html', conv=conv, dia=dia, bloques=bloques, siguiente_letra=siguiente_letra)


@app.route('/rrhh/validar-dni', methods=['GET', 'POST'])
@login_required
@rol_requerido('rrhh')
def rrhh_validar_dni():
    resultado = None
    postulante = None
    if request.method == 'POST':
        dni_manual = request.form.get('dni_manual', '').strip()
        u = Usuario.query.filter_by(dni=dni_manual).first() if dni_manual else None
        p = u.postulante if u else None
        if p:
            postulante = p
            if p.validado_en_fundo:
                resultado = 'ya_validado'
            else:
                p.validado_en_fundo = True
                p.validado_en_fundo_en = datetime.utcnow()
                db.session.commit()
                resultado = 'valido'
        else:
            resultado = 'invalido'
    return render_template('rrhh/validar_dni.html', resultado=resultado, postulante=postulante)



@app.route('/rrhh/usuarios', methods=['GET', 'POST'])
@login_required
@rol_requerido('rrhh')
def rrhh_usuarios():
    if not current_user.es_jefe:
        flash('Solo el jefe de RR.HH. puede gestionar usuarios.', 'danger')
        return redirect(url_for('rrhh_dashboard'))
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'crear':
            dni = request.form.get('dni','').strip()
            correo = request.form.get('correo','').strip()
            nombres = request.form.get('nombres','').strip()
            apellidos = request.form.get('apellidos','').strip()
            celular = request.form.get('celular','').strip()
            cargo = request.form.get('cargo','').strip()
            rol = request.form.get('rol','').strip()
            pwd = request.form.get('password_temporal','').strip()
            if len(dni) != 8 or not dni.isdigit():
                flash('DNI inválido.', 'danger')
            elif Usuario.query.filter_by(dni=dni).first():
                flash('DNI ya registrado.', 'danger')
            elif correo and Usuario.query.filter_by(correo=correo).first():
                flash('Correo ya registrado.', 'danger')
            elif len(pwd) < 6:
                flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            else:
                u = Usuario(dni=dni, nombres=nombres, apellidos=apellidos,
                            celular=celular, correo=correo, cargo=cargo,
                            rol=rol, verificado=True, activo=True,
                            password_temporal=True)
                u.set_password(pwd)
                db.session.add(u)
                db.session.commit()
                flash(f'Usuario {nombres} {apellidos} creado correctamente.', 'success')
        elif accion in ('activar', 'desactivar'):
            uid = request.form.get('usuario_id')
            u = db.session.get(Usuario, int(uid))
            if u:
                u.activo = (accion == 'activar')
                db.session.commit()
                flash('Estado del usuario actualizado.', 'success')
        return redirect(url_for('rrhh_usuarios'))

    usuarios = Usuario.query.filter(Usuario.rol.in_(['rrhh','medico'])).order_by(Usuario.creado_en.desc()).all()
    return render_template('rrhh/usuarios.html', usuarios=usuarios)


@app.route('/rrhh/inducciones', methods=['GET', 'POST'])
@login_required
@rol_requerido('rrhh')
def rrhh_inducciones():
    if not current_user.es_jefe:
        flash('Solo el jefe de RR.HH. puede gestionar inducciones.', 'danger')
        return redirect(url_for('rrhh_dashboard'))
    if request.method == 'POST':
        accion = request.form.get('accion')

        if accion == 'editar_induccion':
            ind_id = int(request.form.get('ind_id'))
            ind = Induccion.query.get_or_404(ind_id)
            ind.titulo      = request.form.get('titulo', '').strip()
            ind.descripcion = request.form.get('descripcion', '').strip()
            ind.video_url   = request.form.get('video_url', '').strip()
            db.session.commit()
            flash('Inducción actualizada.', 'success')

        elif accion == 'agregar_pregunta':
            ind_id = int(request.form.get('ind_id'))
            texto  = request.form.get('texto', '').strip()
            opcion_a = request.form.get('opcion_a', '').strip()
            opcion_b = request.form.get('opcion_b', '').strip()
            opcion_c = request.form.get('opcion_c', '').strip()
            correcta = request.form.get('correcta', 'a')
            if texto and opcion_a and opcion_b and opcion_c:
                db.session.add(PreguntaInduccion(
                    induccion_id=ind_id, texto=texto,
                    opcion_a=opcion_a, opcion_b=opcion_b, opcion_c=opcion_c,
                    respuesta_correcta=correcta))
                db.session.commit()
                flash('Pregunta agregada.', 'success')
            else:
                flash('Completa todos los campos de la pregunta.', 'danger')

        elif accion == 'eliminar_pregunta':
            preg_id = int(request.form.get('preg_id'))
            preg = PreguntaInduccion.query.get_or_404(preg_id)
            ind_id = preg.induccion_id
            total = PreguntaInduccion.query.filter_by(induccion_id=ind_id).count()
            if total <= 3:
                flash('Debe haber al menos 3 preguntas por inducción.', 'danger')
            else:
                db.session.delete(preg)
                db.session.commit()
                flash('Pregunta eliminada.', 'success')

        elif accion == 'editar_pregunta':
            preg_id = int(request.form.get('preg_id'))
            preg = PreguntaInduccion.query.get_or_404(preg_id)
            preg.texto    = request.form.get('texto', '').strip()
            preg.opcion_a = request.form.get('opcion_a', '').strip()
            preg.opcion_b = request.form.get('opcion_b', '').strip()
            preg.opcion_c = request.form.get('opcion_c', '').strip()
            preg.respuesta_correcta = request.form.get('correcta', 'a')
            db.session.commit()
            flash('Pregunta actualizada.', 'success')

        return redirect(url_for('rrhh_inducciones'))

    inducciones = Induccion.query.order_by(Induccion.orden).all()
    return render_template('rrhh/inducciones.html', inducciones=inducciones)

# ── MÉDICO ───────────────────────────────────────────────────────────────────

@app.route('/medico/dashboard')
@login_required
@rol_requerido('medico', 'rrhh')
def medico_dashboard():
    hoy = date.today()
    citas_hoy = (CitaTopico.query
                 .join(BloqueTopico, CitaTopico.bloque_id == BloqueTopico.id)
                 .join(DiaTopico, BloqueTopico.dia_id == DiaTopico.id)
                 .filter(DiaTopico.fecha == hoy, CitaTopico.estado_cita == 'programada')
                 .count())
    pendientes = CitaTopico.query.filter_by(estado_cita='programada').count()
    atendidas_hoy = (CitaTopico.query
                     .join(BloqueTopico, CitaTopico.bloque_id == BloqueTopico.id)
                     .join(DiaTopico, BloqueTopico.dia_id == DiaTopico.id)
                     .filter(DiaTopico.fecha == hoy, CitaTopico.estado_cita == 'atendida')
                     .count())
    return render_template('medico/dashboard.html',
                           citas_hoy=citas_hoy, pendientes=pendientes, atendidas_hoy=atendidas_hoy)


@app.route('/medico/citas')
@login_required
@rol_requerido('medico', 'rrhh')
def medico_citas():
    ver_todas = request.args.get('todas') == '1'
    fecha_str = request.args.get('fecha', str(date.today()))
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        fecha = date.today()
    if ver_todas:
        citas = (CitaTopico.query
                 .join(BloqueTopico, CitaTopico.bloque_id == BloqueTopico.id)
                 .join(DiaTopico, BloqueTopico.dia_id == DiaTopico.id)
                 .order_by(DiaTopico.fecha, BloqueTopico.nombre).all())
    else:
        citas = (CitaTopico.query
                 .join(BloqueTopico, CitaTopico.bloque_id == BloqueTopico.id)
                 .join(DiaTopico, BloqueTopico.dia_id == DiaTopico.id)
                 .filter(DiaTopico.fecha == fecha)
                 .order_by(BloqueTopico.nombre).all())
    return render_template('medico/citas.html', citas=citas,
                           fecha=fecha, fecha_str=fecha_str, ver_todas=ver_todas)


@app.route('/medico/evaluar/<int:cita_id>', methods=['GET', 'POST'])
@login_required
@rol_requerido('medico', 'rrhh')
def medico_evaluar(cita_id):
    cita = CitaTopico.query.get_or_404(cita_id)
    p = cita.postulante
    conv = convocatoria_activa()

    if request.method == 'POST':
        resultado  = request.form.get('resultado')
        observacion = request.form.get('observacion', '').strip()[:500]

        cita.resultado_medico = resultado
        cita.observacion = observacion
        cita.estado_cita = 'atendida'
        cita.atendido_en = datetime.utcnow()

        if resultado == 'apto':
            p.estado_vacante = 'confirmada'
            registrar_historial(p, 'seleccionado', f'Médico: {current_user.nombres} — apto')
            asegurar_codigo_constancia(p)
            db.session.commit()
            flash(f'Postulante marcado como APTO. {mensaje_presentacion(conv)}', 'success')
        else:
            # liberar vacante
            puesto_conv = None
            if conv and p.puesto:
                puesto_conv = PuestoConvocatoria.query.filter_by(
                    convocatoria_id=conv.id, nombre_puesto=p.puesto).first()
            if puesto_conv:
                puesto_conv.vacantes_ocupadas = max(0, puesto_conv.vacantes_ocupadas - 1)
            # reponer cupo del bloque
            if resultado == 'no_asistio' and cita.bloque_rel:
                cita.bloque_rel.cupos_ocupados = max(0, cita.bloque_rel.cupos_ocupados - 1)
            p.estado_vacante = 'liberada'
            estado_final = 'no_se_presento' if resultado == 'no_asistio' else 'no_apto'
            registrar_historial(p, estado_final, f'Resultado: {resultado}')
            db.session.commit()
            flash('Resultado registrado. Vacante liberada.', 'info')

        return redirect(url_for('medico_citas'))

    return render_template('medico/evaluar.html', cita=cita, postulante=p)



@app.route('/medico/postulante/<int:pid>/cita/<int:cita_id>')
@login_required
@rol_requerido('medico', 'rrhh')
def medico_ficha_postulante(pid, cita_id):
    from models import Postulante
    p = Postulante.query.get_or_404(pid)
    return render_template('medico/ficha_postulante.html', postulante=p, cita_id=cita_id)


@app.route('/mi-cuenta', methods=['GET', 'POST'])
@login_required
def mi_cuenta():
    if current_user.rol == 'postulante':
        return redirect(url_for('postulante_dashboard'))
    if request.method == 'POST':
        actual = request.form.get('password_actual', '').strip()
        nueva = request.form.get('password_nueva', '').strip()
        confirmar = request.form.get('password_confirmar', '').strip()
        if not current_user.check_password(actual):
            flash('La contraseña actual es incorrecta.', 'danger')
            return redirect(url_for('mi_cuenta'))
        if len(nueva) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres.', 'danger')
            return redirect(url_for('mi_cuenta'))
        if nueva != confirmar:
            flash('Las contraseñas no coinciden.', 'danger')
            return redirect(url_for('mi_cuenta'))
        current_user.set_password(nueva)
        current_user.password_temporal = False
        db.session.commit()
        flash('Contraseña actualizada correctamente.', 'success')
        return redirect(url_for('dashboard_redirect'))
    return render_template('auth/mi_cuenta.html')



@app.route('/rrhh/postulante/<int:pid>/contrato')
@login_required
@rol_requerido('rrhh')
def rrhh_contrato(pid):
    p = Postulante.query.get_or_404(pid)
    conv = convocatoria_activa()
    return render_template('rrhh/contrato.html', postulante=p, conv=conv)

# ── INIT ─────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    seed_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
