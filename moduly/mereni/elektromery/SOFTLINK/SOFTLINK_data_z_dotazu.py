from playwright.sync_api import sync_playwright
from decouple import config
from datetime import datetime, timedelta
from pathlib import Path


USERNAME = config('SOFTUSE')
PASSWORD = config('SOFTPASS')


def SOFTLINK_dotaz():
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

        # ====== OPRAVA CESTY ======
        auth_path = Path(__file__).resolve().parent / "lds_auth.json"
        auth_path.parent.mkdir(parents=True, exist_ok=True)

        context.storage_state(path=str(auth_path))
        # =========================

        # context.storage_state(path="../lds_auth.json")
        # context.storage_state(path="../elektromery/lds_auth.json")

        od = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
        do = int(datetime.now().timestamp() * 1000)

        od = od
        do_ = do

        SOFTLINK_Json = portal.evaluate("""
                               async ({od, do_}) => {
                                   console.log(document.cookie);

                                   const res = await fetch("https://cem2.softlink.cz/cemapi/api?id=45", {
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

        return SOFTLINK_Json


