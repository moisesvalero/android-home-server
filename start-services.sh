#!/data/data/com.termux/files/usr/bin/sh
# ==============================================================================
# SCRIPT DE AUTO-ARRANQUE PERSISTENTE (Termux:Boot)
# ==============================================================================
# Se ejecuta automáticamente al reiniciar o encender el dispositivo Android.

# 1. Bloqueo de suspensión para mantener la CPU activa con la pantalla apagada
termux-wake-lock

# 2. Iniciar servidor SSH seguro
sshd

# 3. Resucitar todos los procesos gestionados por PM2 (Hermes, DLNA, Dashboard)
pm2 resurrect
