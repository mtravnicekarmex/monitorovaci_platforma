import datetime

# INTERVALY PŘEPOJOVÁNÍ TRAFOSTANIC

# TS1

TS_1_do_2024_01_01_00_00_00 = ['A-1', 'A-2', 'A-3', 'AB-Sps',
                               'B', 'Bk',
                               'ČS', 'DSP',
                               'E', 'F',
                               'G-1', 'G-2.2', 'G-2.3', 'G-2.4', 'G-2.5', 'G-3.1', 'G-SpS',
                               'I-1', 'J',
                               'K-1', 'K-2', 'K-3', 'K-5', 'K-7',
                               'M', 'N', 'O1',
                               'P1', 'P-2, P-3',
                               'T', 'T-EH'
                               ]



INTERVALY_TS_1 = [
    # do 2024-01-01 00:00:00
    (datetime.datetime(2024,1,1,0,0,0), datetime.datetime(2099, 12, 31, 23, 59, 59), TS_1_do_2024_01_01_00_00_00)
    ]



def ziskej_TS_1(datum_str):
    """
    Vrátí seznam elektroměrů na dané TS platný pro zadaný datum a čas.
    """
    # Parse the string to a datetime object if it is a string
    if isinstance(datum_str, str):
        dt = datetime.datetime.strptime(datum_str, '%Y-%m-%d %H:%M:%S')
    else:
        dt = datum_str

    for dt_from, dt_to, seznam in INTERVALY_TS_1:
        if dt_from <= dt <= dt_to:
            return seznam
    return []





# TS2
TS_2_do_2024_01_01_00_00_00 = ['O2', 'Q', 'VO-Q']




INTERVALY_TS_2 = [
    # do 2024-01-01 00:00:00
    (datetime.datetime(2024,1,1,0,0,0), datetime.datetime(2099, 12, 31, 23, 59, 59), TS_2_do_2024_01_01_00_00_00)
    ]



def ziskej_TS_2(datum_str):
    """
    Vrátí seznam elektroměrů na dané TS platný pro zadaný datum a čas.
    """
    # Parse the string to a datetime object if it is a string
    if isinstance(datum_str, str):
        dt = datetime.datetime.strptime(datum_str, '%Y-%m-%d %H:%M:%S')
    else:
        dt = datum_str

    for dt_from, dt_to, seznam in INTERVALY_TS_2:
        if dt_from <= dt <= dt_to:
            return seznam
    return []






# TS3
TS_3_do_2024_01_01_00_00_00 = ['ČSMY',
                               'L1',
                               'L2-1', 'L2-11', 'L2-11-EH', 'L2-2', 'L2-3', 'L2-3-EH',
                               'L2-4', 'L2-5', 'L2-6', 'L2-7-EH',
                               'L3', 'L4', 'L4-EH',
                               'L5', 'L5-EH', 'L6',
                               'L7', 'L7-EH',
                               'VO-L2L3', 'VO-L5L6'
                               ]

INTERVALY_TS_3 = [
    # do 2024-01-01 00:00:00
    (datetime.datetime(2024, 1, 1, 0, 0, 0), datetime.datetime(2099, 12, 31, 23, 59, 59), TS_3_do_2024_01_01_00_00_00)
    ]



def ziskej_TS_3(datum_str):
    """
    Vrátí seznam elektroměrů na dané TS platný pro zadaný datum a čas.
    """
    # Parse the string to a datetime object if it is a string
    if isinstance(datum_str, str):
        dt = datetime.datetime.strptime(datum_str, '%Y-%m-%d %H:%M:%S')
    else:
        dt = datum_str

    for dt_from, dt_to, seznam in INTERVALY_TS_3:
        if dt_from <= dt <= dt_to:
            return seznam
    return []
