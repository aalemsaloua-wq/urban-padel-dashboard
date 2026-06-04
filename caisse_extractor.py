# ==============================================================
#  extractors/caisse_extractor.py
# ==============================================================

import sys, os, re, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from extractors.utils import nettoyer_valeur, lire_date, extraire_mois_annee
from config.mapping import CAISSE_COL_CODE, CAISSE_COL_DEBIT, CAISSE_COL_CREDIT, CAISSE_CODES_CA


def _extraire_date_libelle(libelle: str, annee_feuille: int):
    if not libelle or not isinstance(libelle, str):
        return None
    lib = libelle.upper().strip()

    m = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})', lib)
    if m:
        j, mo, an = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if abs(an - annee_feuille) > 1:
            an = annee_feuille
        try:
            return datetime.date(an, mo, j)
        except ValueError:
            pass

    m = re.search(r'(\d{1,2})[/\-\.](\d{1,2})(?![/\-\.]\d)', lib)
    if m:
        j, mo = int(m.group(1)), int(m.group(2))
        if 1 <= j <= 31 and 1 <= mo <= 12:
            try:
                return datetime.date(annee_feuille, mo, j)
            except ValueError:
                pass

    return None


def _trouver_entete_caisse(lignes: list) -> tuple:
    mots_code   = [c.upper() for c in CAISSE_COL_CODE]
    mots_debit  = [c.upper() for c in CAISSE_COL_DEBIT]
    mots_credit = [c.upper() for c in CAISSE_COL_CREDIT]

    for i, ligne in enumerate(lignes[:20]):
        vals = [str(c).upper().strip() for c in ligne if c is not None]
        if 'DATE' not in vals:
            continue
        if not any(m in vals for m in mots_debit):
            continue

        colonnes = {}
        for j, cell in enumerate(ligne):
            if cell is None:
                continue
            cle = str(cell).upper().strip()
            if cle in mots_code and 'code' not in colonnes:
                colonnes['code'] = j
            elif cle == 'DATE':
                colonnes['date'] = j
            elif cle == 'FNR' and 'fnr' not in colonnes:
                colonnes['fnr'] = j
            elif cle in ('LIBELLÉS','LIBELLE','LIBELLÉ','LIBELLES') and 'libelle' not in colonnes:
                colonnes['libelle'] = j
            elif cle in mots_debit and 'debit' not in colonnes:
                colonnes['debit'] = j
            elif cle in mots_credit and 'credit' not in colonnes:
                colonnes['credit'] = j
            elif cle == 'SOLDE' and 'solde' not in colonnes:
                colonnes['solde'] = j

        if 'date' in colonnes and 'debit' in colonnes:
            return i, colonnes

    return None, {}


def _est_entree_ca(code: str, fnr: str, libelle: str) -> bool:
    """
    Retourne True UNIQUEMENT si cette ligne est une entree CA especes journaliere.
    Accepte : CA DU dd/mm/yyyy, CA DU dd/mm, CHIFFRE D AFFAIRE DU dd/mm
    Exclut  : tournois, ventes materiel, regularisations, etc.
    """
    lib = libelle.upper().strip()

    # Pattern strict : "CA DU dd/mm" ou "CA dd/mm"
    if re.match(r'CA\s+DU\s+\d{1,2}/\d{1,2}', lib):
        return True
    if re.match(r'CA\s+\d{1,2}/\d{1,2}', lib):
        return True

    # Pattern caisse W : "CHIFFRE D'AFFAIRE DU dd/mm" ou "CHIFFRE D AFFAIRE dd/mm"
    if re.match(r"CHIFFRE D['\s]?AFFAIRE[S]?\s+(DU\s+)?\d{1,2}/\d{1,2}", lib):
        return True

    # FNR = CA avec date dans le libelle (caisse W)
    if fnr.upper().strip() == 'CA':
        if re.search(r'\d{1,2}/\d{1,2}', lib):
            return True

    return False


def _lire_feuille_caisse(ws, nom_feuille: str, id_caisse: str) -> list:
    lignes = list(ws.iter_rows(values_only=True))
    idx_entete, colonnes = _trouver_entete_caisse(lignes)

    if idx_entete is None:
        return []

    my = extraire_mois_annee(nom_feuille)
    annee_feuille = my[1] if my else datetime.date.today().year

    mouvements = []
    for ligne in lignes[idx_entete + 1:]:
        if not ligne or len(ligne) <= max(colonnes.values(), default=0):
            continue

        def get(nom):
            if nom in colonnes and colonnes[nom] < len(ligne):
                return ligne[colonnes[nom]]
            return None

        code    = str(get('code')    or '').strip()
        fnr     = str(get('fnr')     or '').strip()
        libelle = str(get('libelle') or '').strip()
        debit   = nettoyer_valeur(get('debit'))
        credit  = nettoyer_valeur(get('credit'))
        solde   = nettoyer_valeur(get('solde'))

        if not _est_entree_ca(code, fnr, libelle):
            continue
        if debit is None or debit <= 0:
            continue

        date_depuis_libelle = _extraire_date_libelle(libelle, annee_feuille)
        date_depuis_col     = lire_date(get('date'))

        if date_depuis_libelle is not None:
            date_val    = date_depuis_libelle
            source_date = 'libelle'
        elif date_depuis_col is not None:
            date_val    = date_depuis_col
            source_date = 'colonne'
        else:
            continue

        mouvements.append({
            'caisse':        id_caisse,
            'feuille':       nom_feuille,
            'date':          date_val,
            'date_colonne':  date_depuis_col,
            'date_libelle':  date_depuis_libelle,
            'source_date':   source_date,
            'code':          code,
            'fnr':           fnr,
            'libelle':       libelle,
            'debit':         debit,
            'credit':        credit,
            'solde':         solde,
            'est_entree_ca': True,
        })

    return mouvements


def extraire_caisse(chemin_fichier: str, id_caisse: str) -> dict:
    print(f'\n  Lecture Caisse {id_caisse}...')
    print(f'  Fichier : {os.path.basename(chemin_fichier)}')

    try:
        wb = openpyxl.load_workbook(chemin_fichier, read_only=True, data_only=True)
    except FileNotFoundError:
        return {'mouvements': [], 'entrees_ca': [], 'nb_mouvements': 0,
                'nb_entrees_ca': 0, 'erreurs': [f'Fichier introuvable : {chemin_fichier}']}
    except Exception as e:
        return {'mouvements': [], 'entrees_ca': [], 'nb_mouvements': 0,
                'nb_entrees_ca': 0, 'erreurs': [f'Impossible d ouvrir : {e}']}

    tous = []
    erreurs = []

    for nom_feuille in wb.sheetnames:
        try:
            ws = wb[nom_feuille]
            mvts = _lire_feuille_caisse(ws, nom_feuille, id_caisse)
            if mvts:
                nb_lib = sum(1 for m in mvts if m['source_date'] == 'libelle')
                nb_col = sum(1 for m in mvts if m['source_date'] == 'colonne')
                print(f'  OK {nom_feuille} -> {len(mvts)} entrees CA '
                      f'(libelle={nb_lib}, colonne={nb_col})')
                tous.extend(mvts)
        except Exception as e:
            erreurs.append(f'Erreur {nom_feuille}: {e}')

    wb.close()
    print(f'  -> Total Caisse {id_caisse} : {len(tous)} entrees CA')

    return {
        'mouvements':    tous,
        'entrees_ca':    tous,
        'nb_mouvements': len(tous),
        'nb_entrees_ca': len(tous),
        'erreurs':       erreurs,
    }
