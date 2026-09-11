---
id: direct-actions-no-confirm-2026-09-11
date: 2026-09-11
status: implemented
---

# Bezpośrednie akcje ticketów w panelu

Przyciski akcji ticketów wykonują operację bez dodatkowego pytania. Dotyczy to
zamknięcia lokalnego ticketu Planfile oraz istniejących przycisków realizacji,
importu i zmiany statusu. Kliknięcie `Zamknij ticket` od razu ustawia status
`done`, odświeża strumień i usuwa ticket z listy otwartych zadań.

Usunięto jedyny frontendowy `window.confirm`. Scenariusz TestQL CLI sprawdza,
że potwierdzenie nie wróci przypadkowo do kontrolera.
