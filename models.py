from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
bcrypt = Bcrypt()


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    dni = db.Column(db.String(8), unique=True, nullable=False)
    nombres = db.Column(db.String(100))          # capturado en registro
    apellidos = db.Column(db.String(100))
    celular = db.Column(db.String(15), nullable=False)
    correo = db.Column(db.String(120), unique=True, nullable=True)  # staff
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)   # postulante | rrhh | medico
    verificado = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)
    otp_expira = db.Column(db.DateTime, nullable=True)
    intentos_fallidos = db.Column(db.Integer, default=0)
    bloqueado_hasta = db.Column(db.DateTime, nullable=True)
    activo = db.Column(db.Boolean, default=True)
    cargo = db.Column(db.String(100), nullable=True)
    password_temporal = db.Column(db.Boolean, default=False)
    es_jefe = db.Column(db.Boolean, default=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    postulante = db.relationship('Postulante', backref='usuario', uselist=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


class Convocatoria(db.Model):
    __tablename__ = 'convocatorias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    fecha_apertura = db.Column(db.DateTime, nullable=False)
    fecha_cierre = db.Column(db.DateTime, nullable=False)
    fecha_presentacion = db.Column(db.Date, nullable=False)
    hora_presentacion = db.Column(db.String(10), nullable=False)
    lugar_presentacion = db.Column(db.String(200), nullable=False)
    activa = db.Column(db.Boolean, default=True)
    cerrada_manualmente = db.Column(db.Boolean, default=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    puestos = db.relationship('PuestoConvocatoria', backref='convocatoria', lazy=True)

    @property
    def total_vacantes(self):
        return sum(p.vacantes_total for p in self.puestos)

    @property
    def vacantes_ocupadas(self):
        return sum(p.vacantes_ocupadas for p in self.puestos)

    @property
    def vacantes_disponibles(self):
        return self.total_vacantes - self.vacantes_ocupadas


class PuestoConvocatoria(db.Model):
    __tablename__ = 'puestos_convocatoria'
    id = db.Column(db.Integer, primary_key=True)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey('convocatorias.id'), nullable=False)
    nombre_puesto = db.Column(db.String(60), nullable=False)
    vacantes_total = db.Column(db.Integer, nullable=False, default=0)
    vacantes_ocupadas = db.Column(db.Integer, default=0)

    @property
    def vacantes_disponibles(self):
        return self.vacantes_total - self.vacantes_ocupadas


class Postulante(db.Model):
    __tablename__ = 'postulantes'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey('convocatorias.id'), nullable=True)

    # Datos personales complementarios
    fecha_nacimiento = db.Column(db.Date)
    sexo = db.Column(db.String(10))
    grado_instruccion = db.Column(db.String(50))
    distrito = db.Column(db.String(60))
    puesto = db.Column(db.String(60))
    es_extrabajador = db.Column(db.Boolean, default=False)
    datos_completos = db.Column(db.Boolean, default=False)

    # Estado del proceso
    estado_proceso = db.Column(db.String(40), default='registrado')
    estado_vacante = db.Column(db.String(30), nullable=True)

    # Trazabilidad
    fecha_hora_declaracion = db.Column(db.DateTime)
    fecha_hora_habilitacion = db.Column(db.DateTime)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    # Validación de presentación en el lugar de trabajo (constancia de habilitación)
    validado_en_fundo = db.Column(db.Boolean, default=False)
    validado_en_fundo_en = db.Column(db.DateTime)
    codigo_constancia = db.Column(db.String(12), unique=True, nullable=True)

    inducciones = db.relationship('AvanceInduccion', backref='postulante', lazy=True)
    declaracion = db.relationship('DeclaracionSalud', backref='postulante', uselist=False)
    cita = db.relationship('CitaTopico', backref='postulante', uselist=False)
    historial = db.relationship('HistorialEstado', backref='postulante', lazy=True)

    @property
    def dni(self):
        return self.usuario.dni if self.usuario else None

    @property
    def nombres(self):
        return self.usuario.nombres if self.usuario else None

    @property
    def apellidos(self):
        return self.usuario.apellidos if self.usuario else None


class Induccion(db.Model):
    __tablename__ = 'inducciones'
    id = db.Column(db.Integer, primary_key=True)
    orden = db.Column(db.Integer, nullable=False)
    titulo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    video_url = db.Column(db.String(300))
    preguntas = db.relationship('PreguntaInduccion', backref='induccion', lazy=True, order_by='PreguntaInduccion.id')


class PreguntaInduccion(db.Model):
    __tablename__ = 'preguntas_induccion'
    id = db.Column(db.Integer, primary_key=True)
    induccion_id = db.Column(db.Integer, db.ForeignKey('inducciones.id'), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    opcion_a = db.Column(db.String(200), nullable=False)
    opcion_b = db.Column(db.String(200), nullable=False)
    opcion_c = db.Column(db.String(200), nullable=False)
    respuesta_correcta = db.Column(db.String(1), nullable=False)


class AvanceInduccion(db.Model):
    __tablename__ = 'avance_induccion'
    id = db.Column(db.Integer, primary_key=True)
    postulante_id = db.Column(db.Integer, db.ForeignKey('postulantes.id'), nullable=False)
    induccion_id = db.Column(db.Integer, db.ForeignKey('inducciones.id'), nullable=False)
    video_completado = db.Column(db.Boolean, default=False)
    aprobado = db.Column(db.Boolean, default=False)
    completado_en = db.Column(db.DateTime)


class DeclaracionSalud(db.Model):
    __tablename__ = 'declaraciones_salud'
    id = db.Column(db.Integer, primary_key=True)
    postulante_id = db.Column(db.Integer, db.ForeignKey('postulantes.id'), nullable=False)
    # antecedentes médicos específicos (True = presenta la condición)
    mayor_65 = db.Column(db.Boolean, default=False)
    hipertension = db.Column(db.Boolean, default=False)
    diabetes = db.Column(db.Boolean, default=False)
    cardiovascular = db.Column(db.Boolean, default=False)
    pulmonar_cronica = db.Column(db.Boolean, default=False)
    cancer = db.Column(db.Boolean, default=False)
    asma = db.Column(db.Boolean, default=False)
    enfisema = db.Column(db.Boolean, default=False)
    epoc = db.Column(db.Boolean, default=False)
    obesidad = db.Column(db.Boolean, default=False)
    gestacion = db.Column(db.Boolean, default=False)
    sin_antecedentes = db.Column(db.Boolean, default=False)
    firmado_en = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def tiene_condicion(self):
        return any([self.mayor_65, self.hipertension, self.diabetes,
                    self.cardiovascular, self.pulmonar_cronica, self.cancer,
                    self.asma, self.enfisema, self.epoc, self.obesidad, self.gestacion])

    @property
    def condiciones_texto(self):
        mapa = {
            'Mayor de 65 años': self.mayor_65,
            'Hipertensión arterial': self.hipertension,
            'Diabetes mellitus': self.diabetes,
            'Enfermedad cardiovascular': self.cardiovascular,
            'Enfermedad pulmonar crónica': self.pulmonar_cronica,
            'Cáncer': self.cancer,
            'Asma': self.asma,
            'Enfisema': self.enfisema,
            'EPOC': self.epoc,
            'Obesidad': self.obesidad,
            'Gestación': self.gestacion,
        }
        activas = [k for k, v in mapa.items() if v]
        return ', '.join(activas) if activas else 'Sin antecedentes'


class DiaTopico(db.Model):
    """Dia de atencion en topico — contiene multiples bloques A, B, C..."""
    __tablename__ = 'dias_topico'
    id = db.Column(db.Integer, primary_key=True)
    convocatoria_id = db.Column(db.Integer, db.ForeignKey('convocatorias.id'), nullable=True)
    fecha = db.Column(db.Date, nullable=False)
    bloques = db.relationship('BloqueTopico', backref='dia', lazy=True, order_by='BloqueTopico.nombre')

    @property
    def tiene_cupos(self):
        return any(b.cupos_disponibles > 0 for b in self.bloques)


class BloqueTopico(db.Model):
    """Bloque horario dentro de un dia de topico (A, B, C...)."""
    __tablename__ = 'bloques_topico'
    id = db.Column(db.Integer, primary_key=True)
    dia_id = db.Column(db.Integer, db.ForeignKey('dias_topico.id'), nullable=False)
    nombre = db.Column(db.String(1), nullable=False)
    hora_inicio = db.Column(db.String(10), nullable=False)
    hora_fin = db.Column(db.String(10), nullable=False)
    cupos_total = db.Column(db.Integer, nullable=False, default=0)
    cupos_ocupados = db.Column(db.Integer, default=0)

    @property
    def cupos_disponibles(self):
        return self.cupos_total - self.cupos_ocupados

    @property
    def etiqueta(self):
        return 'Bloque ' + self.nombre + ' (' + self.hora_inicio + ' - ' + self.hora_fin + ')'



class CitaTopico(db.Model):
    __tablename__ = 'citas_topico'
    id = db.Column(db.Integer, primary_key=True)
    postulante_id = db.Column(db.Integer, db.ForeignKey('postulantes.id'), nullable=False)
    bloque_id = db.Column(db.Integer, db.ForeignKey('bloques_topico.id'), nullable=False)
    estado_cita = db.Column(db.String(20), default='programada')
    resultado_medico = db.Column(db.String(20))
    observacion = db.Column(db.Text)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    atendido_en = db.Column(db.DateTime)

    bloque_rel = db.relationship('BloqueTopico', backref='citas')

    @property
    def dia(self):
        return self.bloque_rel.dia if self.bloque_rel else None

    @property
    def etiqueta_bloque(self):
        if self.bloque_rel:
            return self.bloque_rel.etiqueta
        return ''


class HistorialEstado(db.Model):
    __tablename__ = 'historial_estados'
    id = db.Column(db.Integer, primary_key=True)
    postulante_id = db.Column(db.Integer, db.ForeignKey('postulantes.id'), nullable=False)
    estado_anterior = db.Column(db.String(40))
    estado_nuevo = db.Column(db.String(40))
    descripcion = db.Column(db.String(200))
    registrado_en = db.Column(db.DateTime, default=datetime.utcnow)
