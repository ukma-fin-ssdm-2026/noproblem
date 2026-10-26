-- Виконується автоматично ОДИН раз, коли Docker уперше створює базу
-- (порожній том notely-db). Створює окрему базу для тестів: тести
-- очищають усі таблиці, тож робоча база notely ними не зачіпається.
CREATE DATABASE notely_test;

-- File was created by Claude. Review pending: Kozynska Anastasia
