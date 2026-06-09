import cv2
import tempfile
import time
import platform
import subprocess
import os
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import FONT_PATHS

PRINT_COOLDOWN = 5
_last_print_time = 0


def _load_font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(str(path), size)
        except:
            continue
    return ImageFont.load_default()


def _build_print_image(frame, person_statuses: list) -> Image.Image:
    font_large  = _load_font(28)
    font_normal = _load_font(20)

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img       = Image.fromarray(frame_rgb)
    w, h      = img.size

    line_h  = 30
    panel_h = 80 + len(person_statuses) * line_h
    result  = Image.new("RGB", (w, h + panel_h), (30, 30, 30))
    result.paste(img, (0, 0))

    draw = ImageDraw.Draw(result)
    now  = datetime.now().strftime("%d.%m.%Y  %H:%M:%S")
    draw.text((20, h + 10), f"Дата/время: {now}",
              font=font_large, fill=(255, 255, 255))

    for idx, status in enumerate(person_statuses):
        color = (80, 255, 80) if "Все СИЗ" in status else (255, 80, 80)
        draw.text((20, h + 50 + idx * line_h),
                  f"Чел.{idx+1}: {status}",
                  font=font_normal, fill=color)

    return result


def get_printers() -> list:
    """Возвращает список доступных принтеров"""
    if platform.system() == "Windows":
        import win32print
        flags    = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printers = win32print.EnumPrinters(flags)
        return [p[2] for p in printers]  # только имена
    elif platform.system() == "Linux":
        result = subprocess.run(["lpstat", "-a"], capture_output=True, text=True)
        return [line.split()[0] for line in result.stdout.splitlines()]
    return []


def print_frame(frame, person_statuses: list, printer_name: str = None):
    """
    Печатает кадр с информацией о СИЗ.
    printer_name — имя принтера, если None берёт принтер по умолчанию.
    """
    global _last_print_time

    if time.time() - _last_print_time < PRINT_COOLDOWN:
        print("Печать пропущена — кулдаун не истёк")
        return False

    try:
        img = _build_print_image(frame, person_statuses)

        # Сохраняем во временный файл
        tmp_path = Path("uploads") / f"print_{datetime.now().strftime('%H%M%S')}.jpg"
        img.save(str(tmp_path), "JPEG", quality=95)

        system = platform.system()

        if system == "Windows":
            import win32print
            import win32ui
            from PIL import ImageWin

            # Берём нужный принтер или дефолтный
            if printer_name is None:
                printer_name = win32print.GetDefaultPrinter()

            print(f"Печать на: {printer_name}")

            hprinter = win32print.OpenPrinter(printer_name)
            try:
                hdc = win32ui.CreateDC()
                hdc.CreatePrinterDC(printer_name)
                hdc.StartDoc("PPE Detection")
                hdc.StartPage()

                # Размер страницы принтера
                page_w = hdc.GetDeviceCaps(110)  # HORZRES
                page_h = hdc.GetDeviceCaps(111)  # VERTRES

                # Масштабируем изображение под страницу
                img_resized = img.resize((page_w, page_h), Image.LANCZOS)
                dib = ImageWin.Dib(img_resized)
                dib.draw(hdc.GetHandleOutput(), (0, 0, page_w, page_h))

                hdc.EndPage()
                hdc.EndDoc()
                hdc.DeleteDC()
            finally:
                win32print.ClosePrinter(hprinter)

        elif system == "Linux":
            cmd = ["lp"]
            if printer_name:
                cmd += ["-d", printer_name]
            cmd.append(str(tmp_path))
            subprocess.run(cmd, check=True)

        elif system == "Darwin":
            subprocess.run(["lpr", str(tmp_path)], check=True)

        _last_print_time = time.time()
        print(f"Печать запущена успешно")
        return True

    except Exception as e:
        print(f"Ошибка печати: {e}")
        return False