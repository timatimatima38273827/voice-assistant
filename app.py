import sys
import os
import threading
import time
import tempfile
import winreg
import numpy as np
import customtkinter as ctk
import speech_recognition as sr
import pyperclip
import pyautogui
import sounddevice as sd
import scipy.io.wavfile as wav
from pynput import keyboard

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class AppSettings:
    def __init__(self):
        self.os_type = "Windows 11"
        self.cpu_type = "x86 / x64 (Intel, AMD)"
        self.hotkey_keys = {"ctrl", "shift", "space"}
        self.autostart = False

def set_autostart(enable=True):
    """Управление автозапуском в реестре Windows"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "VoiceTypeAssistant"
    py_path = sys.executable
    script_path = os.path.abspath(__file__)
    cmd = f'"{py_path}w" "{script_path}"'

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Ошибка автозапуска: {e}")

class ConfigWindow(ctk.CTkToplevel):
    """Окно настроек"""
    def __init__(self, parent, settings, on_save_callback):
        super().__init__(parent)

        self.settings = settings
        self.on_save = on_save_callback
        self.captured_keys = set(settings.hotkey_keys)
        self.is_recording_keys = False

        self.title("Настройки Voice Assistant")
        self.geometry("450x520")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        ctk.CTkLabel(
            self, 
            text="Параметры приложения", 
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(15, 10))

        # 1. Выбор ОС
        ctk.CTkLabel(self, text="Операционная система:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=30, pady=(5, 2))
        self.os_menu = ctk.CTkOptionMenu(self, values=["Windows 10", "Windows 11", "macOS"])
        self.os_menu.set(self.settings.os_type)
        self.os_menu.pack(fill="x", padx=30, pady=(0, 10))

        # 2. Выбор процессора
        ctk.CTkLabel(self, text="Архитектура процессора:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=30, pady=(5, 2))
        self.cpu_menu = ctk.CTkOptionMenu(self, values=["x86 / x64 (Intel, AMD)", "ARM64 (Snapdragon / Apple M-series)"])
        self.cpu_menu.set(self.settings.cpu_type)
        self.cpu_menu.pack(fill="x", padx=30, pady=(0, 10))

        # 3. Назначение горячих клавиш
        ctk.CTkLabel(self, text="Горячие клавиши (Зажмите для записи):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=30, pady=(5, 2))
        
        current_str = "+".join(sorted(self.captured_keys)).upper()
        self.key_btn = ctk.CTkButton(
            self, 
            text=f"Клавиши: {current_str} (Нажмите для изменения)", 
            font=ctk.CTkFont(size=12, weight="bold"),
            height=38,
            fg_color="#2C2C2E",
            hover_color="#3A3A3C",
            command=self.start_key_recording
        )
        self.key_btn.pack(fill="x", padx=30, pady=(0, 10))

        # 4. Чекбокс Автозапуска
        self.autostart_var = ctk.BooleanVar(value=self.settings.autostart)
        self.autostart_check = ctk.CTkCheckBox(
            self, 
            text="Запускать при старте системы (Windows)",
            variable=self.autostart_var,
            font=ctk.CTkFont(size=12)
        )
        self.autostart_check.pack(anchor="w", padx=30, pady=10)

        # Сохранение
        ctk.CTkButton(
            self, 
            text="Применить и сохранить", 
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            corner_radius=10,
            command=self.save_settings
        ).pack(fill="x", padx=30, pady=(15, 10))

    def start_key_recording(self):
        self.captured_keys.clear()
        self.is_recording_keys = True
        self.key_btn.configure(text="Зажмите клавиши...", fg_color="#FF9500")

        def on_press(key):
            if not self.is_recording_keys:
                return False
            
            try:
                k_name = key.char.lower() if hasattr(key, 'char') and key.char else key.name.lower()
            except Exception:
                k_name = str(key).lower().replace("key.", "")

            if "ctrl" in k_name: k_name = "ctrl"
            elif "shift" in k_name: k_name = "shift"
            elif "alt" in k_name: k_name = "alt"
            elif "cmd" in k_name or "win" in k_name: k_name = "cmd"

            self.captured_keys.add(k_name)
            keys_str = "+".join(sorted(self.captured_keys)).upper()
            self.key_btn.configure(text=f"Зажато: {keys_str}")

        def stop_listener():
            time.sleep(1.8)
            self.is_recording_keys = False
            if self.captured_keys:
                keys_str = "+".join(sorted(self.captured_keys)).upper()
                self.key_btn.configure(text=f"Назначено: {keys_str}", fg_color="#34C759")
            else:
                self.key_btn.configure(text="Нажмите для изменения", fg_color="#2C2C2E")

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        threading.Thread(target=stop_listener, daemon=True).start()

    def save_settings(self):
        self.settings.os_type = self.os_menu.get()
        self.settings.cpu_type = self.cpu_menu.get()
        if self.captured_keys:
            self.settings.hotkey_keys = self.captured_keys
        self.settings.autostart = self.autostart_var.get()

        if "Windows" in self.settings.os_type:
            set_autostart(self.settings.autostart)

        self.on_save(self.settings)
        self.destroy()

class VoiceWidget(ctk.CTk):
    """Главный виджет диктовки с поддержкой Push-to-Talk (запись по удержанию)"""
    def __init__(self):
        super().__init__()

        self.settings = AppSettings()
        self.recognizer = sr.Recognizer()
        self.is_recording = False
        self.current_pressed = set()
        self.audio_frames = []
        self.stream = None
        self.config_window = None

        self.title("Voice Assistant")
        self.geometry("320x130")
        self.minsize(240, 110)
        self.attributes("-topmost", True)

        self.frame = ctk.CTkFrame(self, corner_radius=12)
        self.frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Верхняя панель со статусом и кнопкой настроек ⚙️
        self.top_bar = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.top_bar.pack(fill="x", padx=10, pady=(5, 0))

        hotkey_str = "+".join(sorted(self.settings.hotkey_keys)).upper()
        self.status_label = ctk.CTkLabel(
            self.top_bar, 
            text=f"Удерживайте: {hotkey_str}", 
            font=ctk.CTkFont(size=11),
            text_color="#8E8E93"
        )
        self.status_label.pack(side="left")

        self.settings_btn = ctk.CTkButton(
            self.top_bar,
            text="⚙️",
            width=28,
            height=24,
            fg_color="transparent",
            hover_color="#3A3A3C",
            command=self.open_settings
        )
        self.settings_btn.pack(side="right")

        # Основная кнопка записи
        self.btn = ctk.CTkButton(
            self.frame,
            text="🎤 Удерживайте клавиши",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            corner_radius=10,
            command=lambda: None
        )
        self.btn.pack(fill="x", padx=12, pady=(5, 8))

        self.start_global_hotkey_listener()

    def open_settings(self):
        if self.config_window is None or not self.config_window.winfo_exists():
            self.config_window = ConfigWindow(self, self.settings, self.update_after_settings)
        else:
            self.config_window.focus()

    def update_after_settings(self, new_settings):
        self.settings = new_settings
        hotkey_str = "+".join(sorted(self.settings.hotkey_keys)).upper()
        self.status_label.configure(text=f"Удерживайте: {hotkey_str}")

    def start_global_hotkey_listener(self):
        def normalize_key(key):
            try:
                k_name = key.char.lower() if hasattr(key, 'char') and key.char else key.name.lower()
            except Exception:
                k_name = str(key).lower().replace("key.", "")

            if "ctrl" in k_name: return "ctrl"
            if "shift" in k_name: return "shift"
            if "alt" in k_name: return "alt"
            if "cmd" in k_name or "win" in k_name: return "cmd"
            return k_name

        def on_press(key):
            k = normalize_key(key)
            self.current_pressed.add(k)
            
            # Если все горячие клавиши зажаты и запись еще не идет — НАЧИНАЕМ ЗАПИСЬ
            if self.settings.hotkey_keys.issubset(self.current_pressed) and not self.is_recording:
                self.start_recording()

        def on_release(key):
            k = normalize_key(key)
            if k in self.current_pressed:
                self.current_pressed.remove(k)

            # Если была отжата хотя бы одна из горячих клавиш — ОСТАНАВЛИВАЕМ ЗАПИСЬ
            if self.is_recording and not self.settings.hotkey_keys.issubset(self.current_pressed):
                self.stop_recording()

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()

    def audio_callback(self, indata, frames, time, status):
        """Непрерывно записываем звук, пока клавиши зажаты"""
        if self.is_recording:
            self.audio_frames.append(indata.copy())

    def start_recording(self):
        self.is_recording = True
        self.audio_frames = []
        
        self.btn.configure(text="🔴 Идет запись...", fg_color="#FF3B30")
        self.status_label.configure(text="Говорите...", text_color="#FF3B30")

        self.stream = sd.InputStream(samplerate=44100, channels=1, dtype='int16', callback=self.audio_callback)
        self.stream.start()

    def stop_recording(self):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        self.btn.configure(text="⚙️ Обработка...", fg_color="#FFCC00")
        self.status_label.configure(text="Распознаём...", text_color="#FFCC00")

        threading.Thread(target=self.process_audio, daemon=True).start()

    def process_audio(self):
        if not self.audio_frames:
            self.reset_ui_state()
            return

        wav_path = None
        try:
            audio_data = np.concatenate(self.audio_frames, axis=0)
            
            # Сохраняем во временный файл
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            wav_path = temp_file.name
            wav.write(wav_path, 44100, audio_data)

            # Распознаем
            with sr.AudioFile(wav_path) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio, language="ru-RU")

            pyperclip.copy(text)
            
            if "macOS" in self.settings.os_type:
                pyautogui.hotkey('command', 'v')
            else:
                pyautogui.hotkey('ctrl', 'v')

            self.btn.configure(text="✅ Вставлено!", fg_color="#34C759")
            self.status_label.configure(text=f"Текст: {text[:15]}...", text_color="#34C759")

        except sr.UnknownValueError:
            self.btn.configure(text="⚠️ Не понял", fg_color="#FF9500")
            self.status_label.configure(text="Слишком коротко / нет речи", text_color="#FF9500")
        except Exception:
            self.btn.configure(text="⚠️ Ошибка", fg_color="#FF3B30")
            self.status_label.configure(text="Ошибка обработки", text_color="#FF3B30")
        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

            time.sleep(1.2)
            self.reset_ui_state()

    def reset_ui_state(self):
        self.btn.configure(text="🎤 Удерживайте клавиши", fg_color=["#3B8ED0", "#1F6AA5"])
        hotkey_str = "+".join(sorted(self.settings.hotkey_keys)).upper()
        self.status_label.configure(text=f"Удерживайте: {hotkey_str}", text_color="#8E8E93")

if __name__ == "__main__":
    app = VoiceWidget()
    app.mainloop()