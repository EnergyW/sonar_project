import os
import subprocess
from pathlib import Path
import sys

def compile_translations():
    locale_dir = Path("")
    print(f"Поиск .po файлов в {locale_dir.resolve()}...")

    compiled_count = 0
    error_count = 0

    for po_path in locale_dir.rglob("*/LC_MESSAGES/bot.po"):
        lang_dir = po_path.parent
        mo_path = lang_dir / "bot.mo"

        with open(po_path, 'rb') as f:
            first_bytes = f.read(3)
            first_lines = f.read(200).decode('utf-8', errors='replace').split('\n')[:3]

        print(f"\nАнализ файла: {po_path}")
        print(f"Первые 3 байта: {first_bytes}")
        print("Первые строки файла:")
        for i, line in enumerate(first_lines[:3], 1):
            print(f"{i}: {line}")

        if first_bytes == b'\xef\xbb\xbf':
            print("⚠️ Обнаружен BOM (Byte Order Mark) в начале файла! Это может вызывать ошибки.")
            print("Рекомендуется сохранить файл в UTF-8 без BOM")

        try:
            print(f"Попытка компиляции: {po_path} -> {mo_path}")
            result = subprocess.run(
                ["msgfmt", "-o", str(mo_path), str(po_path)],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )

            if result.returncode == 0:
                print("✅ Компиляция успешна!")
                compiled_count += 1
            else:
                error_count += 1
                print(f"❌ Ошибка компиляции (код {result.returncode}):")
                print(result.stderr)

                # Вывод проблемных строк
                with open(po_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        print("\nПервая строка файла:", lines[0].strip())
                        print("Строка 135:", lines[134].strip() if len(lines) > 134 else "<файл слишком короткий>")

        except Exception as e:
            error_count += 1
            print(f"❌ Фатальная ошибка: {str(e)}")
            if "msgfmt" in str(e):
                print("\nУбедитесь, что gettext установлен и доступен в PATH:")
                print("  Windows: скачайте и установите gettext отсюда:")
                print("           https://github.com/mlocati/gettext-iconv-windows/releases")
                print("           и добавьте bin/ в PATH")
                print("  Linux: sudo apt-get install gettext")
                print("  macOS: brew install gettext")

    print(f"\nИтог: Скомпилировано: {compiled_count}, Ошибок: {error_count}")
    if error_count > 0:
        print("\nРекомендации по исправлению:")
        print("1. Убедитесь, что файлы сохранены в UTF-8 без BOM")
        print("2. Проверьте синтаксис в указанных строках (1 и 135)")
        print("3. Проверьте, что все строки начинаются с правильных директив (msgid, msgstr)")
        print("4. Убедитесь, что нет незакрытых кавычек")
        print("5. Проверьте пустые строки в конце файла - их не должно быть")
        print("6. Для проверки файла используйте команду: msgfmt -c ваш_файл.po")


if __name__ == "__main__":
    compile_translations()