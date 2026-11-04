# Changelog

All notable changes to this project are documented in this file.

## [0.1.0] (стан до)

Початковий стан проєкту до рефакторингів Лабораторної 8.

## [0.1.1] - 2026-11-04

### Refactoring

- **Extract Function**: винесено спільне правило визначення ролі для
  схвалених запитів на доступ.
- **Replace Magic Number with Constant**: значення тайм-ауту та розмірів пулу
  PostgreSQL винесено в іменовані константи.
- **Replace Conditional with Map**: відповідність винятків і HTTP-відповідей
  перенесено в таблицю.
