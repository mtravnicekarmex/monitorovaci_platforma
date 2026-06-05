<?php require_once __DIR__ . '/../../includes/admin_check.php'; ?>
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Admin – ARMEX Map</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { overflow: hidden; }
    #sidebar {
  position: fixed;
  top: 56px;            /* výška horní lišty */
  left: 0;
  bottom: 0;
  width: 220px;         /* pevná šířka */
  overflow-y: auto;     /* scroll, pokud by byl obsah dlouhý */
  background-color: #f8f9fa;
  border-right: 1px solid #dee2e6;
}

#main {
  margin-left: 220px;   /* sidebar */
  margin-top: 16px;     /* topbar */
  height: calc(100vh - 56px);
  overflow-y: auto;
  padding: 1rem;
   width: 100%;
}

#main .placeholder-wrap {
  height: 100%;
  display: flex;
  justify-content: center;   /* horizontálně */
  align-items: center;       /* vertikálně */
}

#main .placeholder {
  text-align: center;
  font-size: 1.25rem;
}


    #sidebar .nav-link.active { background-color: #0d6efd; color: #fff; }
	
	.brand {
  font: 700 24px/1.1 system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif;
  letter-spacing: .5px;
  margin: 0;
}

.brand-arm { color: #E10600; }  /* červená */
.brand-ex  { color: #0070F3; }  /* modrá  */
  </style>
</head>
<body>
  <!-- horní lišta -->
  <nav class="navbar navbar-dark bg-dark">
    <div class="container-fluid">
      <span class="navbar-brand mb-0 h1"><span class="brand-arm">ARM</span><span class="brand-ex">EX</span> map – Admin</span>
      <a href="/armex/public/dashboard.php" class="btn btn-outline-light btn-sm">Dashboard</a>
    </div>
  </nav>

  <div class="d-flex">
    <!-- sidebar -->
    <div id="sidebar" class="bg-light border-end vh-100">
      <nav class="nav flex-column p-2">
        <a class="nav-link" href="#" data-url="settings.php">⚙️ Aplikace & DB</a>
        <a class="nav-link" href="#" data-url="layers.php">🗂 Data & filtry</a>
		<a class="nav-link" href="#" data-url="basemaps.php">🗺️ Mapové vrstvy</a>
        <a class="nav-link" href="#" data-url="versionlog.php">📜 Version log</a>
      </nav>
    </div>

    <!-- hlavní obsah -->
    <div id="main">
  <div class="placeholder-wrap">
    <div class="placeholder">Vyberte položku z menu vlevo…</div>
  </div>
</div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  <script>
 const main = document.getElementById('main');
const links = document.querySelectorAll('#sidebar .nav-link');

links.forEach(link => {
  link.addEventListener('click', async e => {
    e.preventDefault();
    loadPage(link);
  });
});

async function loadPage(link) {
  links.forEach(l => l.classList.remove('active'));
  link.classList.add('active');
  main.innerHTML = '<div class="text-muted p-3">Načítám…</div>';
  try {
    const resp = await fetch(link.dataset.url, {credentials:'same-origin'});
    if (!resp.ok) throw new Error('HTTP '+resp.status);
    const html = await resp.text();
    main.innerHTML = html;
    runScripts(main);
  } catch(err) {
    main.innerHTML = `<div class="text-danger p-3">Chyba načítání: ${err}</div>`;
  }
}

function runScripts(container){
  container.querySelectorAll("script").forEach(oldScript => {
    const s = document.createElement("script");
    if (oldScript.src) {
      s.src = oldScript.src;
    } else {
      s.textContent = oldScript.textContent;
    }
    document.body.appendChild(s);
    oldScript.remove();
  });
}

// 👉 Defaultně načti "settings"
document.addEventListener('DOMContentLoaded', () => {
  const first = document.querySelector('#sidebar .nav-link[data-url="settings.php"]');
  if (first) loadPage(first);
});
  </script>
</body>
</html>
