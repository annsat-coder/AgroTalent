# AgroTalent — Sistema de Reclutamiento Digital

Prototipo web para reclutamiento de operarios temporales en una empresa agroindustrial.

## Stack
- Python + Flask
- SQLite (local) / PostgreSQL (producción)
- Bootstrap 5

## Cómo ejecutar localmente

```bash
# 1. Crear entorno virtual
python -m venv venv

# Windows CMD:
venv\Scripts\activate.bat

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar
python app.py
```

Abrir en el navegador: http://localhost:5000

## Accesos de prueba

| Rol | DNI | Contraseña |
|-----|-----|------------|
| RR.HH. | 00000001 | rrhh1234 |
| Médico | 00000002 | medico1234 |
| Postulante | Regístrate tú mismo | — |

## Usar PostgreSQL (opcional)

Crea un archivo `.env` con:
```
DATABASE_URL=postgresql://usuario:contraseña@localhost:5432/agrotalent
SECRET_KEY=clave-secreta
```

## Publicar en Render

1. Subir a GitHub
2. Crear servicio Web en render.com
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Agregar variable `DATABASE_URL` con tu PostgreSQL (Render ofrece PostgreSQL gratuito)

## Estructura del proyecto

```
agrotalent/
├── app.py              # Rutas Flask (todas)
├── models.py           # Modelos SQLAlchemy
├── seed.py             # Datos iniciales
├── requirements.txt
├── static/
│   └── css/main.css    # Estilos globales (colores, fuentes, responsive)
└── templates/
    ├── base.html        # Layout base con navbar
    ├── index.html       # Pantalla de bienvenida
    ├── auth/            # Login y registro
    ├── postulante/      # Dashboard, datos, inducciones, declaración, constancia
    ├── rrhh/            # Dashboard, postulantes, campañas, tópico, validación
    └── medico/          # Dashboard, agenda, evaluación
```

## Qué modificar para personalizar

| Qué cambiar | Dónde |
|-------------|-------|
| Colores del sistema | `static/css/main.css` — variables `:root` |
| Distritos, puestos, grados | `app.py` — listas dentro de `postulante_datos()` |
| Preguntas de inducción | `seed.py` — sección `inducciones_data` |
| Número de vacantes por defecto | `seed.py` — `vacantes_total` en Campaña |
| Horarios de tópico iniciales | `seed.py` — lista `horarios` |
| Textos de la declaración jurada | `templates/postulante/declaracion.html` |
| Nota mínima para aprobar inducción | `app.py` — `puntaje >= 60` en `postulante_induccion_detalle()` |
