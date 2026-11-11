# Radar actions : guide pas à pas

Ce projet analyse tes actions toutes les 15 minutes, met à jour un tableau de bord web et t'envoie une notification sur ton téléphone quand quelque chose bouge. Tout tourne gratuitement sur GitHub, sans serveur.

## 1. Notifications sur ton téléphone (ntfy)
1. Installe l'application **ntfy** (iPhone ou Android).
2. Appuie sur « + » et abonne-toi à un sujet au **nom long et aléatoire**, par exemple `radar-many-7fk2x9qpa81`. Quiconque connaît ce nom peut lire tes alertes : garde-le secret.

## 2. Mettre le projet sur GitHub
1. Crée un compte sur github.com.
2. Clique sur **New repository**, nomme-le `radar`, choisis **Public** (obligatoire pour l'hébergement gratuit), puis crée-le.
3. Clique sur **uploading an existing file** et glisse tout le contenu du dossier décompressé.
4. Si le dossier `.github` n'apparaît pas (dossier caché), clique sur **Add file > Create new file**, tape `.github/workflows/run.yml` comme nom et colle le contenu du fichier `run.yml`.

## 3. Réglages (une seule fois)
1. **Settings > Secrets and variables > Actions > New repository secret** : nom `NTFY_TOPIC`, valeur = ton sujet ntfy.
2. **Settings > Pages** : Source = « Deploy from a branch », branche `main`, dossier `/docs`, puis Save.
3. **Settings > Actions > General > Workflow permissions** : choisis « Read and write permissions ».

## 4. Premier lancement
1. Onglet **Actions > Analyse > Run workflow**, coche « test » : tu dois recevoir une notification sur ton téléphone.
2. Relance **sans** cocher « test » : les données se créent en 1 à 2 minutes.
3. Ton tableau de bord est sur `https://TON-PSEUDO.github.io/radar/`. Ajoute-le à l'écran d'accueil de ton téléphone.

## Personnaliser
Modifie `config.yaml` (bouton crayon sur GitHub) : actions, concurrents, seuils d'alerte. Symboles Yahoo : `.PA` Paris, `.DE` Allemagne, `.L` Londres, rien pour les USA.

## Limites à connaître
- Données différées d'environ 15 minutes, et GitHub peut retarder une exécution de 5 à 30 minutes.
- Yahoo Finance bloque parfois les serveurs cloud : si une exécution échoue, la précédente est conservée.
- Le dépôt est public : ta liste d'actions est visible de ceux qui trouvent l'adresse.
- Le score est un indicateur automatique, pas un conseil en investissement.
