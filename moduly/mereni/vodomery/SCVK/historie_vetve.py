import datetime

# INTERVALY PŘEPOJOVÁNÍ VODOVODNÍCH VĚTVÍ

# větev HECHT

vetev_L_do_2025_09_23_23_59_59 = ['L0_V1', 'L1_V1', 'L4_V1', 'L5_V1', 'L6_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7']
vetev_L_od_2025_09_24_00_00_00_do_2025_11_25_07_59_59 = ['L0_V1', 'L1_V1', 'L4_V1', 'L5_V1', 'L6_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7', 'CS_V2']
vetev_L_od_2025_11_25_08_00_00_do_2025_12_04_11_44_59 = ['L0_V1', 'L1_V1', 'L4_V1', 'L5_V1', 'L6_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7', 'CS_V2', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']
vetev_L_od_2025_12_04_11_45_00_do_2025_12_04_13_29_59 = ['L0_V1', 'L1_V1', 'L5_V1', 'L6_V1']
vetev_L_od_2025_12_04_13_30_00_do_2025_12_08_09_51_59 = ['L0_V1', 'L1_V1', 'L5_V1', 'L6_V1', 'CS_V2', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']
vetev_L_od_2025_12_08_09_52_00_do_2025_12_09_12_04_59 = ['L0_V1', 'L1_V1', 'L5_V1', 'L6_V1', 'CS_V2', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1', 'L4_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7']
vetev_L_od_2025_12_09_12_05_00_do_2025_12_12_15_19_59 = ['L0_V1', 'L1_V1', 'L5_V1', 'L6_V1', 'CS_V2', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7']
vetev_L_od_2025_12_12_15_20_00_do_2025_12_17_13_29_59 = ['L0_V1', 'L1_V1', 'L5_V1', 'L6_V1', 'CS_V2', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']
vetev_L_od_2025_12_17_13_30_00 = ['L0_V1', 'L1_V1', 'L5_V1', 'L6_V1']


INTERVALY_vetev_L = [
    # do 2025-09-23 23:59:59
    (datetime.datetime(2025,4,1,0,0,0), datetime.datetime(2025, 9, 23, 23, 59, 59), vetev_L_do_2025_09_23_23_59_59),
    # od 2025-09-24 00:00:00 .. 2025-11-24 07:59:59
    (datetime.datetime(2025, 9, 24, 0, 0, 0), datetime.datetime(2025, 11, 25, 7, 59, 59), vetev_L_od_2025_09_24_00_00_00_do_2025_11_25_07_59_59),
    # od 2025-11-25 08:00:00 .. 2025-12-04 11:44:59
    (datetime.datetime(2025, 11, 25, 8, 0, 0), datetime.datetime(2025, 12, 4, 11, 44, 59), vetev_L_od_2025_11_25_08_00_00_do_2025_12_04_11_44_59),
    # od 2025-12-04 11:45:00 .. 2025-12-04 13:29:59
    (datetime.datetime(2025, 12, 4, 11, 45, 0), datetime.datetime(2025, 12, 4, 13, 29, 59), vetev_L_od_2025_12_04_11_45_00_do_2025_12_04_13_29_59),
    # od 2025-12-04 13:30:00 .. 2025-12-08 09:51:59
    (datetime.datetime(2025, 12, 4, 13, 30, 0), datetime.datetime(2025, 12, 8, 9, 51, 59), vetev_L_od_2025_12_04_13_30_00_do_2025_12_08_09_51_59),
    # od 2025-12-08 09:52:00 .. 2025-12-09 12:04:59
    (datetime.datetime(2025, 12, 8, 9, 52, 0), datetime.datetime(2025, 12, 9, 12, 4, 59), vetev_L_od_2025_12_08_09_52_00_do_2025_12_09_12_04_59),
    # od 2025-12-09 12:05:00 . . 2025-12-12 15:19:59
    (datetime.datetime(2025, 12, 9, 12, 5, 0), datetime.datetime(2025, 12, 12, 15, 19, 59), vetev_L_od_2025_12_09_12_05_00_do_2025_12_12_15_19_59),
    # od 2025-12-12 15:20:00 . . 2025-12-17 13:29:59
    (datetime.datetime(2025, 12, 12, 15, 20, 0), datetime.datetime(2025, 12, 17, 13, 29, 59), vetev_L_od_2025_12_12_15_20_00_do_2025_12_17_13_29_59),
    # od 2025-12-17 13:30:00 dále
    (datetime.datetime(2025, 12, 17, 13, 30, 0), datetime.datetime(2099, 12, 31, 23, 59, 59), vetev_L_od_2025_12_17_13_30_00)
    ]




def ziskej_vetev_L(datum_str):
    """
    Vrátí seznam větví platný pro zadaný datum a čas.
    """
    # Parse the string to a datetime object if it is a string
    if isinstance(datum_str, str):
        dt = datetime.datetime.strptime(datum_str, '%Y-%m-%d %H:%M:%S')
    else:
        dt = datum_str

    for dt_from, dt_to, seznam in INTERVALY_vetev_L:
        if dt_from <= dt <= dt_to:
            return seznam
    return []






# větev DOKTOR VODA

vetev_dok_voda_od_2026_01_19_10_59_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3']


INTERVALY_vetev_dok_voda = [
    # od 2026-01-19 11:00:00
    (datetime.datetime(2026, 1, 19, 11, 0, 0), datetime.datetime(2099, 12, 31, 23, 59, 59), vetev_dok_voda_od_2026_01_19_10_59_59)]



def ziskej_vetev_dok_voda(datum_str):
    """
    Vrátí seznam větví platný pro zadaný datum a čas.
    """
    # Parse the string to a datetime object if it is a string
    if isinstance(datum_str, str):
        dt = datetime.datetime.strptime(datum_str, '%Y-%m-%d %H:%M:%S')
    else:
        dt = datum_str

    for dt_from, dt_to, seznam in INTERVALY_vetev_dok_voda:
        if dt_from <= dt <= dt_to:
            return seznam
    return []





# větev DOKTOR POŽÁRNÍ VODA

vetev_dok_poz_voda_do_2025_09_23_23_59_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1']
vetev_dok_poz_voda_od_2025_09_24_00_00_00_do_2025_11_25_07_59_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1']
vetev_dok_poz_voda_od_2025_11_25_08_00_00_do_2025_12_04_11_44_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1']
vetev_dok_poz_voda_od_2025_12_04_11_45_00_do_2025_12_04_13_29_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1', 'L4_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7', 'CS_V2', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']
vetev_dok_poz_voda_od_2025_12_04_13_30_00_do_2025_12_08_09_51_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1', 'L4_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7']
vetev_dok_poz_voda_od_2025_12_08_09_52_00_do_2025_12_09_12_04_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1']
vetev_dok_poz_voda_od_2025_12_09_12_05_00_do_2025_12_12_15_19_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1', 'L4_V1', 'L7_V1']
vetev_dok_poz_voda_od_2025_12_12_15_20_00_do_2025_12_17_13_29_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1', 'L4_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7']
vetev_dok_poz_voda_od_2025_12_17_13_30_00_do_2026_01_19_10_59_59 = ['K_V1', 'K_V2', 'K_V3', 'J_V1', 'I_V1', 'N_V1', 'O_V1', 'P_V1', 'P_V2', 'T_V1', 'G_V1', 'G_V2', 'G_V3', 'F_V1', 'E_V1', 'L4_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7', 'CS_V2', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']
vetev_dok_poz_voda_od_2026_01_19_11_00_00 = ['E_V1', 'F_V1', 'L4_V1', 'L7_V1', 'L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7', 'CS_V2', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']



INTERVALY_vetev_dok_poz_voda = [
    # do 2025-09-23 23:59:59
    (datetime.datetime(2025,4,1,0,0,0), datetime.datetime(2025, 12, 4, 11, 44, 59), vetev_dok_poz_voda_do_2025_09_23_23_59_59),
    # od 2025-09-24 00:00:00 .. 2025-11-25 07:59:59
    (datetime.datetime(2025, 9, 24, 0, 0, 0), datetime.datetime(2025, 11, 25, 7, 59, 59), vetev_dok_poz_voda_od_2025_09_24_00_00_00_do_2025_11_25_07_59_59),
    # od 2025-11-25 08:00:00 .. 2025-12-04 11:44:59
    (datetime.datetime(2025, 11, 25, 8, 0, 0), datetime.datetime(2025, 12, 4, 11, 44, 59), vetev_dok_poz_voda_od_2025_11_25_08_00_00_do_2025_12_04_11_44_59),
    # od 2025-12-04 11:45:00 .. 2025-12-04 13:29:59
    (datetime.datetime(2025, 12, 4, 11, 45, 0), datetime.datetime(2025, 12, 4, 13, 29, 59), vetev_dok_poz_voda_od_2025_12_04_11_45_00_do_2025_12_04_13_29_59),
    # od 2025-12-04 13:30:00 .. 2025-12-08 09:51:59
    (datetime.datetime(2025, 12, 4, 13, 30, 0), datetime.datetime(2025, 12, 8, 9, 51, 59), vetev_dok_poz_voda_od_2025_12_04_13_30_00_do_2025_12_08_09_51_59),
    # od 2025-12-08 9:52:00 .. 2025-12-09 12:04:59
    (datetime.datetime(2025, 12, 8, 9, 52, 0), datetime.datetime(2025, 12, 9, 12, 4, 59), vetev_dok_poz_voda_od_2025_12_08_09_52_00_do_2025_12_09_12_04_59),
    # od 2025-12-09 12:05:00 .. 2025-12-15 15:19:59
    (datetime.datetime(2025, 12, 9, 12, 5, 0), datetime.datetime(2025, 12, 12, 15, 19, 59), vetev_dok_poz_voda_od_2025_12_09_12_05_00_do_2025_12_12_15_19_59),
    # od 2025-12-12 15:20:00 .. 2025-12-17 13:29:59
    (datetime.datetime(2025, 12, 12, 15, 20, 0), datetime.datetime(2025, 12, 17, 13, 29, 59), vetev_dok_poz_voda_od_2025_12_12_15_20_00_do_2025_12_17_13_29_59),
    # od 2025-12-17 13:30:00 .. 2026-01-19 10:59:59
    (datetime.datetime(2025, 12, 17, 13, 30, 0), datetime.datetime(2026, 1, 19, 10, 59, 59), vetev_dok_poz_voda_od_2025_12_17_13_30_00_do_2026_01_19_10_59_59),
    # od 2026-01-19 11:00:00 .. dále
    (datetime.datetime(2026, 1, 19, 11, 00, 0), datetime.datetime(2099, 12, 31, 23, 59, 59), vetev_dok_poz_voda_od_2026_01_19_11_00_00)
    ]



def ziskej_vetev_dok_poz_voda(datum_str):
    """
    Vrátí seznam větví platný pro zadaný datum a čas.
    """
    # Parse the string to a datetime object if it is a string
    if isinstance(datum_str, str):
        dt = datetime.datetime.strptime(datum_str, '%Y-%m-%d %H:%M:%S')
    else:
        dt = datum_str

    for dt_from, dt_to, seznam in INTERVALY_vetev_dok_poz_voda:
        if dt_from <= dt <= dt_to:
            return seznam
    return []





# větev GROBÁR

vetev_grobar_do_2025_09_23_23_59_59 = ['CS_V1', 'CS_V2', 'DSP_V1', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']
vetev_grobar_od_2025_09_24_00_00_00_do_2025_11_25_07_59_59 = ['CS_V1', 'DSP_V1', 'B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']
vetev_grobar_od_2025_11_25_08_00_00 = ['CS_V1', 'DSP_V1', 'B0_V1']


INTERVALY_vetev_grobar = [
    # do 2025-09-23 23:59:59
    (datetime.datetime(2025,4,1,0,0,0), datetime.datetime(2025, 9, 23, 23, 59, 59), vetev_grobar_do_2025_09_23_23_59_59),
    # od 2025-09-24 00:00:00 .. 2025-11-24 07:59:59
    (datetime.datetime(2025, 9, 24, 0, 0, 0), datetime.datetime(2025, 11, 25, 7, 59, 59), vetev_grobar_od_2025_09_24_00_00_00_do_2025_11_25_07_59_59),
    # od 2025-11-25 08:00:00 .. dále
    (datetime.datetime(2025, 11, 25, 8, 0, 0), datetime.datetime(2099, 12, 31, 23, 59, 59), vetev_grobar_od_2025_11_25_08_00_00)
    ]


def ziskej_vetev_grobar(datum_str):
    """
    Vrátí seznam větví platný pro zadaný datum a čas.
    """
    # Parse the string to a datetime object if it is a string
    if isinstance(datum_str, str):
        dt = datetime.datetime.strptime(datum_str, '%Y-%m-%d %H:%M:%S')
    else:
        dt = datum_str

    for dt_from, dt_to, seznam in INTERVALY_vetev_grobar:
        if dt_from <= dt <= dt_to:
            return seznam
    return []



budova_E = ['E_V2', 'E_V3', 'E_V4', 'E_V5']
budova_B = ['B_V1', 'B_V2', 'B_V3', 'B_V4', 'B_V5', 'Bk_V1', 'Bk_V2', 'A_V1']
budova_A = ['A_V2', 'A_V3']
budova_L2L3 = ['L2-L3_V1', 'L2-L3_V2', 'L2-L3_V3', 'L2-L3_V4', 'L2-L3_V5', 'L2-L3_V6', 'L2-L3_V7']

