from playwright.sync_api import sync_playwright
from decouple import config
# import requests
# from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from icecream import ic
import pandas as pd

USERNAME = config('SOFTUSE')
PASSWORD = config('SOFTPASS')

SOFTLINK_ZARIZENI_COLUMNS = [
    "me_id",
    "me_desc",
    "me_serial",
    "me_typ_pzn",
    "me_plom",
    "me_zapoc",
    "mis_id",
    "met_id",
    "me_od",
    "me_do",
    "me_over",
]
SOFTLINK_DATE_COLUMNS = ["me_od", "me_do", "me_over"]







def SOFTLINK_dotaz_zarizeni():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://ldsportal.softlink.cz")

        with page.expect_popup() as popup_info:
            page.get_by_role("link", name="Vstoupit do portálu").click()

        portal = popup_info.value

        portal.get_by_role("textbox", name="Přístupové jméno").fill(USERNAME)
        portal.get_by_role("textbox", name="Přístupové heslo").fill(PASSWORD, timeout=30000)
        portal.get_by_role("button", name="Přihlásit").click()

        portal.wait_for_selector("text=Odhlásit")

        print("✅ Úspěšně přihlášen")

        context.storage_state(path="lds_auth.json")

        od = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
        do = int(datetime.now().timestamp() * 1000)

        od = od
        do_ = do

        SOFTLINK_Json = portal.evaluate("""
                                        async ({od, do_}) => {
                                            console.log(document.cookie);

                                            const res = await fetch("https://cem2.softlink.cz/cemapi/api?id=46", {
                                                method: "POST",
                                                credentials: "include",
                                                headers: {
                                                    "Content-Type": "application/json"
                                                },
                                                body: JSON.stringify({
                                                    mit_id: 105,
                                                    od: od,
                                                    do: do_,
                                                    typ: "DEN"
                                                })
                                            });

                                            return {
                                                status: res.status,
                                                data: await res.json()
                                            };
                                        }
                                        """, {"od": od, "do_": do_})

        portal.wait_for_timeout(5000)

        browser.close()

        ic(SOFTLINK_Json)

        return SOFTLINK_Json

