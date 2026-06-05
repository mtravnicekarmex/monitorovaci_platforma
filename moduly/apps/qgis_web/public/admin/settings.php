<?php require_once __DIR__ . '/../../includes/admin_check.php'; ?>
<!doctype html><html lang="cs"><head>
<meta charset="utf-8"><title>Admin – Nastavení</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head><body>
<div class="container py-4">

  <form id="frmSettings" class="card p-3">
    <div class="mb-2"><label class="form-label">App Base</label><input name="app_base" class="form-control"></div>
    <h6 class="mt-3">Databáze</h6>
    <div class="row g-2">
      <div class="col-md-3"><input class="form-control" name="db_driver" placeholder="pgsql"></div>
      <div class="col-md-3"><input class="form-control" name="db_host" placeholder="127.0.0.1"></div>
      <div class="col-md-2"><input class="form-control" name="db_port" placeholder="5432"></div>
      <div class="col-md-4"><input class="form-control" name="db_name" placeholder="armex"></div>
      <div class="col-md-4"><input class="form-control" name="db_user" placeholder="armex_user"></div>
      <div class="col-md-4"><input class="form-control" name="db_pass" placeholder="***" type="password"></div>
    </div>
    <div class="mt-3 d-flex gap-2">
      <button class="btn btn-primary">Uložit</button>




    </div>
  </form>

<button id="test-db-btn" class="btn btn-primary" style="margin-top:10px;">
    Otestovat DB připojení
</button>

<div id="test-db-result" style="margin-top:10px;font-weight:bold;"></div>
</div>
<script>

document.getElementById("test-db-btn")?.addEventListener("click", () => {
    const resBox = document.getElementById("test-db-result");
    resBox.innerHTML = "Testuji…";

    fetch("api/test_db.php")
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                resBox.style.color = "green";
                resBox.innerHTML = "✔ " + data.message + "<br>Server time: " + data.server_time;
            } else {
                resBox.style.color = "red";
                resBox.innerHTML = "✖ Chyba: " + data.message;
            }
        })
        .catch(err => {
            resBox.style.color = "red";
            resBox.innerHTML = "✖ Chyba při volání API: " + err;
        });
});


async function load(){
  const r = await fetch('api/get_config.php');
  const cfg = await r.json();
  const db  = cfg.settings.db;
  const f = document.getElementById('frmSettings');

  f.db_driver.value = db.driver;
  f.db_host.value   = db.host;
  f.db_port.value   = db.port;
  f.db_name.value   = db.dbname;
  f.db_user.value   = db.user;
  f.db_pass.value   = ""; // heslo zpět neukazujeme
}



document.getElementById('frmSettings').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const fd = new FormData(e.target);

  const payload = {
    app_base: fd.get('app_base'),
    db: {
      driver: fd.get('db_driver'),
      host:   fd.get('db_host'),
      port:   Number(fd.get('db_port')),
      dbname: fd.get('db_name'),
      user:   fd.get('db_user'),
      pass:   fd.get('db_pass')
    }
  };


  const res = await fetch('api/save_db_config.php', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });

  const out = await res.json();
  if (!out.ok) return alert('Uložení selhalo: ' + out.msg);
  alert('Uloženo');
});



load();
</script>
</body></html>
