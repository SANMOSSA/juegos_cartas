FROM python:3.11

# 📌 2. Crear directorio de trabajo
WORKDIR /app

# 📌 3. Copiar solo requirements.txt para cachear instalación de Python deps
COPY requirements.txt .

# 📌 4. Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# 📌 6. Copiar SOLO ahora el resto del código (no rompe caché de deps)
COPY . .


# 📌 8. Exponer puerto
EXPOSE 8005

# 📌 9. Comando por defecto
CMD ["python", "app.py"]