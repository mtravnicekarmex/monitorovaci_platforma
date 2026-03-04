import pandas as pd
from decouple import config
from core.db.connect import ENGINE_MS, ENGINE_PG, SessionLocalPG, SessionLocalMS
from moduly.mereni.vodomery.database.models import *
from moduly.mereni.elektromery.database.models import *
from sqlalchemy import select






def SCVK_PG_database_nyni():
    """ database with SCVK data from Postgre database """
    SCVK_database_nyni = pd.read_sql_table('Mereni_vodomery_SCVK', con=ENGINE_PG, schema=config('PGSCHEMADBO'), index_col='recid')

    return SCVK_database_nyni


def SCVK_PG_zarizeni_nyni():
    """ database with SCVK data from Postgre database """
    SCVK_zarizeni_nyni = pd.read_sql_table('Zarizeni_vodomery_SCVK', con=ENGINE_PG, schema=config('PGSCHEMADBO'), index_col='id')

    return SCVK_zarizeni_nyni


def SCVK_PG_alarmy_nyni():
    """ database with SCVK data from Postgre database """
    SCVK_Alarmy_nyni = pd.read_sql_table('Alarmy_vodomery_SCVK', con=ENGINE_PG, schema=config('PGSCHEMADBO'), index_col='recid')

    return SCVK_Alarmy_nyni


def PG_vodomery_DB_nyni():
    """ database with SCVK data from Postgre database """
    query = """SELECT * FROM "dbo"."Mereni_vodomery_SCVK" """
    PG_database_nyni = pd.read_sql_query(sql=query, con=ENGINE_PG, schema=config('PGSCHEMADBO'), index_col='recid')

    return PG_database_nyni



def PG_vodomery_DB_nyni_join():
    query = (
        select(
            Vodomer_SCVK_Mereni.date,
            Vodomer_SCVK_Mereni.objem,
            Vodomer_SCVK_Zarizeni.identifikace,
            Vodomer_SCVK_Mereni.seriove_cislo
        )
        .join(
            Vodomer_SCVK_Zarizeni,
            Vodomer_SCVK_Mereni.seriove_cislo == Vodomer_SCVK_Zarizeni.seriove_cislo
        )
        .order_by(Vodomer_SCVK_Mereni.date.asc())
    )

    with SessionLocalPG() as session:
        result = session.execute(query)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())

    return df



def PG_elektromery_DB_nyni_join():
    query = (
        select(
            Elektromer_areal_Mereni.date,
            Elektromer_areal_Zarizeni.identifikace,
            Elektromer_areal_Mereni.seriove_cislo,
            Elektromer_areal_Zarizeni.EAN,
            Elektromer_areal_Mereni.vt,
            Elektromer_areal_Mereni.nt,
            Elektromer_areal_Mereni.total,
            Elektromer_areal_Zarizeni.softlink_id,

        )
        .join(
            Elektromer_areal_Zarizeni,
            Elektromer_areal_Mereni.softlink_id == Elektromer_areal_Zarizeni.softlink_id
        )
        .order_by(Elektromer_areal_Mereni.date.asc())
    )

    with SessionLocalMS() as session:
        result = session.execute(query)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())

    return df




def PG_plynomery_DB_nyni_join():
    query = (
        select(
            Plynomer_areal_Mereni.date,
            Plynomer_areal_Mereni.objem,
            Plynomer_areal_Zarizeni.identifikace,
            Plynomer_areal_Mereni.seriove_cislo
        )
        .join(
            Plynomer_areal_Zarizeni,
            Plynomer_areal_Mereni.seriove_cislo == Plynomer_areal_Zarizeni.seriove_cislo
        )
        .order_by(Plynomer_areal_Mereni.date.asc())
    )

    with SessionLocalMS() as session:
        result = session.execute(query)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())

    return df





def MS_vodomery_DB_nyni():
    df = pd.read_sql_table(
        'Mereni_vodomery',
        con=ENGINE_MS,
        schema=config('MSSCHEMA'),
        index_col='recid'
    )

    return df


def MS_elektromery_DB_nyni():
    df = pd.read_sql_table(
        'Mereni_elektromery_areal',
        con=ENGINE_MS,
        schema=config('MSSCHEMA'),
        index_col='recid'
    )

    return df

def MS_plynomery_DB_nyni():
    df = pd.read_sql_table(
        'Mereni_plynomery',
        con=ENGINE_MS,
        schema=config('MSSCHEMA'),
        index_col='recid'
    )

    return df



def MS_kalorimetry_DB_nyni():
    df = pd.read_sql_table(
        'Mereni_Kalorimetr',
        con=ENGINE_MS,
        schema=config('MSSCHEMA'),
        index_col='recid'
    )

    return df


def MS_manometry_DB_nyni():
    df = pd.read_sql_table(
        'Mereni_manometry',
        con=ENGINE_MS,
        schema=config('MSSCHEMA'),
        index_col='recid'
    )

    return df




def df_vodomery_vse_join():
    """ database with SCVK data from MS SQL database """
    df_vse = pd.concat([PG_vodomery_DB_nyni_join(), MS_vodomery_DB_nyni()])
    df_vse.sort_values(by=['date'], inplace=True, ascending=True)
    df_vse['seriove_cislo'] = df_vse['seriove_cislo'].astype(str)

    return df_vse


# def df_vse_join_datum(od=None):
#     """ database with SCVK data from MS SQL database """
#     df_vse_datum = pd.concat([PG_vodomery_DB_nyni_join(), MS_vodomery_DB_nyni()])
#     df_vse_datum.sort_values(by=['date'], inplace=True, ascending=True)
#     df_vse_datum['seriove_cislo'] = df_vse_datum['seriove_cislo'].astype(str)
#     df_vse_datum = df_vse_datum[(df_vse_datum['date'] >= od)]
#
#     return df_vse_datum


def df_elektromery_vse_join():
    """ database with SCVK data from MS SQL database """
    df_vse = PG_elektromery_DB_nyni_join()
    df_vse.sort_values(by=['date'], inplace=True, ascending=True)
    df_vse['seriove_cislo'] = df_vse['seriove_cislo'].astype(str)

    return df_vse





def df_plynomery_vse_join():
    """ database with SCVK data from MS SQL database """
    # df_vse = PG_plynomery_DB_nyni_join()
    df_vse = MS_plynomery_DB_nyni()
    df_vse.sort_values(by=['date'], inplace=True, ascending=True)
    df_vse['seriove_cislo'] = df_vse['seriove_cislo'].astype(str)

    return df_vse


def df_kalorimetry_vse_join():
    """ database with SCVK data from MS SQL database """
    # df_vse = PG_plynomery_DB_nyni_join()
    df_vse = MS_kalorimetry_DB_nyni()
    df_vse = df_vse.rename(columns={'datum': 'date'})
    df_vse.sort_values(by=['date'], inplace=True, ascending=True)
    df_vse['seriove_cislo'] = df_vse['seriove_cislo'].astype(str)

    return df_vse


def df_manometry_vse_join():
    """ database with SCVK data from MS SQL database """
    # df_vse = PG_plynomery_DB_nyni_join()
    df_vse = MS_manometry_DB_nyni()
    df_vse.sort_values(by=['date'], inplace=True, ascending=True)
    df_vse['seriove_cislo'] = df_vse['seriove_cislo'].astype(str)

    return df_vse




