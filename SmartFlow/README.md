# SmartFlow — MVP

Работающий локальный прототип обработки и согласования счетов и презентация из 12 слайдов.

## Скачать

[Скачать весь комплект ZIP](https://github.com/morifox/proizvodstvennyi_menedzhment/raw/refs/heads/main/SmartFlow/smartflow.zip)

- [Презентация PowerPoint](SmartFlow_MVP.pptx)
- [Презентация PDF](SmartFlow_MVP.pdf)
- [Модель MVP](Модель_MVP.md)
- [Инструкция и исходный код](prototype/README.md)

## Linux Mint

Распакуйте архив, откройте терминал в папке `prototype` и выполните:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
bash start.sh
```

Откройте http://127.0.0.1:8000. При первом запуске требуется интернет для установки зависимостей. Остановка — Ctrl+C; данные сохраняются локально.

Приложение извлекает реквизиты из текстовых PDF, DOCX и TXT по правилам, позволяет проверить их, согласовать счёт или вернуть на исправление и выгрузить CSV. ML, OCR и внешние интеграции в эту версию не входят. Роли демонстрируются в одном интерфейсе.
