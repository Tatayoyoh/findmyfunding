# Requirements - FindMyFundings

## Statut : En cours de développement initial

---

## R1 - Consultation des financements (MVP)
**Statut : Implémenté**

Une application web permettant à une structure (association, ONG, coopérative, etc.) d'accéder facilement à tous les financements auxquels elle a accès.

### R1.1 - Recherche et filtrage
- [x] Recherche plein texte (FTS5) sur tous les champs
- [x] Filtrage par catégorie de financement
- [x] Filtrage par montant (min/max)
- [x] Résultats affichés sous forme de cartes avec résumé
- [ ] Filtrage par type de structure éligible
- [ ] Filtrage par thème/domaine

### R1.2 - Fiche détaillée
- [x] Page de détail par programme avec toutes les informations
- [x] Liens vers les sources externes
- [x] Affichage des montants, co-financement, dates limites
- [x] Tags structures éligibles et thèmes

### R1.3 - Import des données
- [x] Import depuis le fichier Excel `Cartographie des financements.xlsx`
- [x] Gestion des cellules fusionnées (catégories, programmes multi-lignes)
- [x] Extraction des hyperlinks

---

## R2 - Mise à jour automatique des financements
**Statut : Implémenté (base)**

Mise à jour régulière (mensuelle) des financements via les sources du document.

### R2.1 - Scraping des sources
- [x] Scraping HTTP des URLs sources avec détection de changements (hash)
- [x] Extraction du contenu textuel des pages HTML
- [ ] Support des fichiers PDF
- [ ] Gestion des erreurs et retry

### R2.2 - Extraction IA
- [x] Utilisation de Claude API pour extraire les données structurées
- [x] Extraction : montants, structures éligibles, thèmes, dates, type de candidature
- [ ] Revue humaine des extractions avant mise à jour

### R2.3 - Planification
- [x] Scraping automatique mensuel (APScheduler, 1er du mois)
- [x] Scraping manuel depuis l'interface admin
- [ ] Notifications en cas de changements détectés

---

## R3 - Ajout simplifié de sources
**Statut : Implémenté (base)**

Pouvoir ajouter une source simplement, et qu'un automatisme ou une IA la parcoure pour en extraire les avantages pour les structures.

### R3.1 - Interface d'ajout
- [x] Formulaire admin : coller une URL → analyse automatique IA
- [ ] Revue/édition des données extraites avant validation
- [ ] Catégorisation automatique ou assistée

### R3.2 - Monitoring
- [x] Table `monitored_sources` avec hash de contenu et date de check
- [x] Liste des sources dans l'interface admin
- [ ] Dashboard de l'état des sources (actives, en erreur, modifiées)

---

## R4 - API programmatique
**Statut : Implémenté**

- [x] GET /api/programs - Liste tous les programmes
- [x] GET /api/programs/{id} - Détail d'un programme
- [x] GET /api/search - Recherche avec filtres
- [x] GET /api/categories - Liste des catégories
- [ ] Authentification API
- [ ] Pagination

---

## R5 - Fonctionnalités futures (non commencées)

### R5.1 - Profils de structures
- [ ] Création d'un profil de structure (type, taille, domaine, localisation)
- [ ] Recommandation personnalisée de financements selon le profil
- [ ] Sauvegarde de favoris / alertes

### R5.2 - Collaboration
- [ ] Multi-utilisateurs avec authentification
- [ ] Partage de recherches / listes de financements
- [ ] Commentaires/notes sur les programmes

### R5.3 - Améliorations IA
- [ ] Matching IA entre profil structure et financements disponibles
- [ ] Résumé automatique des appels à projets
- [ ] Aide à la rédaction de dossiers de financement

### R5.4 - Déploiement et opérations
- [ ] Containerisation (Docker)
- [ ] CI/CD
- [ ] Backup automatique de la base de données
- [ ] Monitoring et alerting
