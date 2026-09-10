# Tickety należą do Planfile

Runtime używa semcod/planfile per projekt, w `.planfile/`. Alokację PLF-ID,
statusy, historię i trwałe powiązania wykonuje natywny Store Planfile.

`ticket.json` jest historycznym szkicem wymagań Gitive, nie formatem aktywnego
ticketu. Nie importuj go jako bazy ticketów ani nie alokuj na jego podstawie ID.
Wspólny adapter `gitive.planfile_bridge` obsługuje trzech wykonawców i jawne
push/pull przez natywny GitHubBackend. Worktree i zgody na publikację podlegają
niezależnym zasadom repozytorium.
