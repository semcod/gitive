# Szablon workspace

`workspace.json` jest deklaracją docelowego środowiska, nie poleceniem uruchomienia.
Wersje runtime i digest obrazu mają wartość null, dopóki nie ustali ich inwentaryzacja.
Profil browser/control może istnieć bez projektu (`project_refs: []`).

Dane wdrożenia należą do prywatnego magazynu poza repo: manifest, kopia danych,
środowisko, profile, logi i dowody weryfikacji. Nie zapisuj sekretów w deklaracji.
Schemat kontroluje kształt danych; nie sprawdza faktycznego działania kontenera.
