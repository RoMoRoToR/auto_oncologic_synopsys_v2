import os
import re
import json
from src.config import Config
from src.collector import DrugDataCollector

def clean_key(key: str) -> str:
    if not key:
        return ""
    # Удаляем всё, кроме латиницы, цифр, дефисов и подчеркиваний
    cleaned = re.sub(r'[^a-zA-Z0-9\-_]', '', key)
    return cleaned

def main():
    # Загружаем переменные из файла .env в окружение (os.environ)
    # 1. Настройка окружения (пути кэша и прочее)
    Config.setup_windows_env()
    
    # 2. Подготовка ключей
    # Ключи Tavily (для поиска в вебе)
    raw_tavily = os.getenv("TAVILY_API_KEY")
    if not raw_tavily:
        raise ValueError("TAVILY_API_KEY environment variable is required")
    tavily_key = clean_key(raw_tavily)
    
    # Ключи Yandex AI Studio (от ребят из чата)
    yandex_folder_id = os.getenv("YANDEX_FOLDER_ID")
    yandex_auth_key = os.getenv("YANDEX_AUTH_KEY")
    if not yandex_folder_id or not yandex_auth_key:
        raise ValueError("YANDEX_FOLDER_ID and YANDEX_AUTH_KEY environment variables are required")

    print(f"[*] Инициализация системы...")
    print(f"[*] Используем Tavily key: {tavily_key[:10]}...")
    print(f"[*] Используем Yandex Folder ID: {yandex_folder_id}")

    # 3. Инициализация коллектора с новыми параметрамi
    # Убедитесь, что ваш DrugDataCollector.__init__ принимает эти 3 ключа
    collector = DrugDataCollector(
        tavily_key=tavily_key, 
        yandex_folder_id=yandex_folder_id, 
        yandex_auth_key=yandex_auth_key
    )
# Ривароксабан Rivaroxaban 20 мг
# Урсодезоксихолиевая кислота Ursodeoxycholic acid 250 мг
# Омепразол Omeprazole 20 мг
# Дапаглифлозин Dapagliflozin 10 мг
# Семаглутид Semaglutide 7 мг
# Апиксабан Apixaban 5 мг
# Азилсартан Azilsartan 80 мг
# Бисопролол Bisoprolol 5 мг 
# Каптоприл Captopril 25 мг
# Диклофенак Diclofenac 50 мг
# Вальпроевая кислота Valproic acid 500 мг
    # Список препаратов для теста
    test_drugs = [
        {"name": "Rivaroxaban", "dosage": "20 mg", "file": None}, 
        {"name": "Ursodeoxycholic acid", "dosage": "250 mg", "file": None},
        {"name": "Omeprazole", "dosage": "20 mg", "file": None},
        {"name": "Dapagliflozin", "dosage": "10 mg", "file": None},
        {"name": "Semaglutide", "dosage": "7 mg", "file": None},
        {"name": "Apixaban", "dosage": "5 mg", "file": None},
        {"name": "Azilsartan", "dosage": "80 mg", "file": None},
        {"name": "Bisoprolol", "dosage": "5 mg", "file": None},
        {"name": "Captopril", "dosage": "25 mg", "file": None},
        {"name": "Diclofenac", "dosage": "50 mg", "file": None},
        {"name": "Valproic acid", "dosage": "500 mg", "file": None},
    ]

    for drug in test_drugs:
        print(f"\n{'='*60}")
        print(f"🚀 ОБРАБОТКА ПРЕПАРАТА: {drug['name']} ({drug['dosage']})")
        
        try:
            # Вызываем основной пайплайн (Tavily + Scholar + Docling + YandexGPT)
            result = collector.get_drug_info(
                drug_name=drug['name'], 
                dosage=drug['dosage'], 
                source_path=drug.get('file')
            )
            
            # Вывод результата
            print("\n✅ ИТОГОВЫЕ ДАННЫЕ (YandexGPT + RAG):")
            print(json.dumps(result, indent=4, ensure_ascii=False))
            
        except Exception as e:
            print(f"\n❌ Критическая ошибка при обработке {drug['name']}:")
            print(f"Тип ошибки: {type(e).__name__}")
            print(f"Детали: {e}")

if __name__ == "__main__":
    main()