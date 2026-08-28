# Plataforma EDUCAR 🚀 [![Django CI/CD Pipeline](https://github.com/rubenguerra/educar)](https://github.com/rubenguerra/educar)

Ecosistema de aprendizaje en línea inteligente desarrollado con Django, Django Channels y WebSockets.

### 🛠️ Características Principales
* **Módulos Multimedia Polimórficos:** Soporte para contenidos tipo texto, video, imágenes y Quizzes en una sola relación modular.
* **Tutoría Inteligente (IA):** Chatbot asíncrono e interactivo conectado a OpenAI (`gpt-4o-mini`) con memoria conversacional y conocimiento integrado del material del curso.
* **Panel Docente (Learning Analytics):** Generación automática de reportes ejecutivos en Markdown que agrupan las dudas teóricas más recurrentes del grupo estudiantil.
* **Control de Calidad Integrado:** Pruebas unitarias y asíncronas con auditoría de cobertura usando `coverage` por encima de los estándares de la industria.

### 🧪 Ejecución de Pruebas Locales
Para correr el suite de pruebas con análisis de cobertura en tu computadora local:
```bash
coverage run --source=chat,students --omit=.venv/*,venv/* manage.py test chat students
coverage report
```
