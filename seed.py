import random, string
from datetime import date, datetime, timedelta
from models import db, Usuario, Convocatoria, PuestoConvocatoria, Induccion, PreguntaInduccion, DiaTopico, BloqueTopico

PUESTOS_DEFAULT = ['Siembra', 'Guiado', 'Poda', 'Desbrote', 'Acomodo',
                   'Desoje', 'Ajuste', 'Descole', 'Raleo', 'Cosecha']

def seed_db():
    # ── Staff ──────────────────────────────────────────────────────────────
    if not Usuario.query.filter_by(dni='00000001').first():
        rrhh = Usuario(dni='00000001', nombres='Administrador', apellidos='RR.HH.',
                       celular='999000001', correo='rrhh@proagro.pe',
                       rol='rrhh', verificado=True, activo=True, es_jefe=True, password_temporal=False)
        rrhh.set_password('rrhh1234')
        db.session.add(rrhh)

    if not Usuario.query.filter_by(dni='00000002').first():
        medico = Usuario(dni='00000002', nombres='Dr. Juan', apellidos='Pérez',
                         celular='999000002', correo='medico@proagro.pe',
                         rol='medico', verificado=True, activo=True)
        medico.set_password('medico1234')
        db.session.add(medico)

    # ── Convocatoria activa ─────────────────────────────────────────────────
    if not Convocatoria.query.first():
        conv = Convocatoria(
            nombre='Campaña Cosecha 2026-I',
            fecha_apertura=datetime(2026, 5, 1, 8, 0),
            fecha_cierre=datetime(2026, 6, 30, 18, 0),
            fecha_presentacion=date(2026, 6, 1),
            hora_presentacion='06:30',
            lugar_presentacion='Fundo ProAgro — Km 12 Carretera Piura-Chulucanas',
            activa=True
        )
        db.session.add(conv)
        db.session.flush()
        vacantes = [20, 10, 8, 15, 12, 5, 8, 6, 10, 6]
        for nombre, v in zip(PUESTOS_DEFAULT, vacantes):
            db.session.add(PuestoConvocatoria(
                convocatoria_id=conv.id, nombre_puesto=nombre, vacantes_total=v))

        # Dia de topico = fecha de presentacion de la convocatoria
        dia = DiaTopico(convocatoria_id=conv.id, fecha=conv.fecha_presentacion)
        db.session.add(dia)
        db.session.flush()
        db.session.add(BloqueTopico(dia_id=dia.id, nombre='A', hora_inicio='08:00', hora_fin='10:00', cupos_total=15))
        db.session.add(BloqueTopico(dia_id=dia.id, nombre='B', hora_inicio='10:00', hora_fin='12:00', cupos_total=15))

    # ── Inducciones ─────────────────────────────────────────────────────────
    if not Induccion.query.first():
        data = [
            {
                'orden': 1, 'titulo': 'Seguridad y Salud Ocupacional',
                'descripcion': 'Normas de seguridad para proteger tu integridad y la de tus compañeros en campo y planta.',
                'video_url': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
                'preguntas': [
                    {'texto': '¿Qué equipo de protección es obligatorio en el área de cosecha?',
                     'a': 'Casco, guantes y botas de seguridad', 'b': 'Solo guantes', 'c': 'Ninguno', 'correcta': 'a'},
                    {'texto': '¿Qué debes hacer ante un accidente de trabajo?',
                     'a': 'Continuar trabajando', 'b': 'Reportar inmediatamente al supervisor', 'c': 'Esperar al final del turno', 'correcta': 'b'},
                    {'texto': '¿Con qué frecuencia se realizan simulacros de evacuación?',
                     'a': 'Nunca', 'b': 'Una vez al año', 'c': 'Según el plan de seguridad', 'correcta': 'c'},
                ]
            },
            {
                'orden': 2, 'titulo': 'Calidad',
                'descripcion': 'Estándares de calidad de ProAgro y su impacto en las certificaciones internacionales.',
                'video_url': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
                'preguntas': [
                    {'texto': '¿Qué certificación de calidad maneja ProAgro?',
                     'a': 'ISO 9001', 'b': 'GlobalGAP', 'c': 'Ambas son correctas', 'correcta': 'c'},
                    {'texto': '¿Qué haces si detectas un producto con defecto?',
                     'a': 'Ignorarlo', 'b': 'Separarlo y comunicarlo al supervisor', 'c': 'Desecharlo sin reportar', 'correcta': 'b'},
                    {'texto': '¿Por qué es importante el control de calidad?',
                     'a': 'Para cumplir normas internacionales', 'b': 'Solo para aumentar precios', 'c': 'No es importante', 'correcta': 'a'},
                ]
            },
            {
                'orden': 3, 'titulo': 'Bienestar Social',
                'descripcion': 'Beneficios, derechos laborales y programas de apoyo para trabajadores temporales.',
                'video_url': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
                'preguntas': [
                    {'texto': '¿Tienes derecho a descanso durante la jornada?',
                     'a': 'No', 'b': 'Sí, según la ley laboral peruana', 'c': 'Solo si el supervisor lo permite', 'correcta': 'b'},
                    {'texto': '¿A qué servicio de salud tienes acceso como trabajador temporal?',
                     'a': 'Solo al tópico interno', 'b': 'EsSalud durante el contrato', 'c': 'Ninguno', 'correcta': 'b'},
                    {'texto': '¿Qué haces si un problema personal afecta tu trabajo?',
                     'a': 'Renunciar directamente', 'b': 'Comunicarte con Bienestar Social', 'c': 'Ignorarlo', 'correcta': 'b'},
                ]
            },
            {
                'orden': 4, 'titulo': 'Recursos Humanos',
                'descripcion': 'Procedimientos de contratación, asistencia, pagos y normas de conducta.',
                'video_url': 'https://www.youtube.com/embed/dQw4w9WgXcQ',
                'preguntas': [
                    {'texto': '¿Cómo se registra tu asistencia diaria?',
                     'a': 'Con huella dactilar o tarjeta', 'b': 'Solo con firma en papel', 'c': 'No se registra', 'correcta': 'a'},
                    {'texto': '¿Cuándo se realiza el pago de remuneraciones?',
                     'a': 'Cada dos semanas', 'b': 'Al final del contrato', 'c': 'Según el cronograma del contrato', 'correcta': 'c'},
                    {'texto': '¿Qué conducta está prohibida en ProAgro?',
                     'a': 'Usar el uniforme completo', 'b': 'Consumir alcohol o sustancias prohibidas', 'c': 'Reportar incidentes', 'correcta': 'b'},
                ]
            },
        ]
        for d in data:
            ind = Induccion(orden=d['orden'], titulo=d['titulo'],
                            descripcion=d['descripcion'], video_url=d['video_url'])
            db.session.add(ind)
            db.session.flush()
            for p in d['preguntas']:
                db.session.add(PreguntaInduccion(
                    induccion_id=ind.id, texto=p['texto'],
                    opcion_a=p['a'], opcion_b=p['b'], opcion_c=p['c'],
                    respuesta_correcta=p['correcta']
                ))

    db.session.commit()
