<?php
require_once __DIR__ . '/../includes/auth_check.php';
?>
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title><?= APP_NAME ?> – Mapa</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" rel="stylesheet">
  <link href="/armex/public/assets/css/styles.css" rel="stylesheet">
  
  <style>
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
  <!-- Horní lišta -->
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark" style="position: sticky; top: 0; z-index: 1000;">
    <div class="container-fluid">

      <a class="navbar-brand navbar-brand mb-0 h1" href="#"><span class="brand-arm">ARM</span><span class="brand-ex">EX</span> map <font size="0.5">verze 1.0.1</font></a>
      <div class="ms-auto d-flex align-items-center">
        <span class="navbar-text text-light small me-3">
          <?= htmlspecialchars($_SESSION['user']['email']) ?>
        </span>
        <a class="btn btn-sm btn-outline-light" href="/armex/public/logout.php">Odhlásit</a>
		
		<?php if (!empty($_SESSION['user']) && $_SESSION['user']['role']==='admin'): ?>
        <a href="/armex/public/admin/" class="btn btn-outline-light btn-sm ms-2">
          Admin
        </a>
      <?php endif; ?>
	  
      </div>
    </div>
  </nav>

  <!-- Layout: sidebar + mapa -->
  <div class="d-flex" id="appLayout">
    <!-- Sidebar -->
<aside id="sidebar" class="border-end bg-white">
  <div class="p-3">
    <h6 class="text-uppercase text-muted">Vrstvy</h6>
    <div id="layersList" class="mb-3"></div>
    <hr>
    <h6 class="text-uppercase text-muted">Filtry</h6>
    <div class="mb-2">
      <label class="form-label">Budova</label>
      <select id="filterBudova" class="form-select form-select-sm">
        <option value="">– všechny –</option>
      </select>
    </div>
    <div class="mb-2">
      <label class="form-label">Patro</label>
      <select id="filterPatro" class="form-select form-select-sm">
        <option value="">– všechna –</option>
      </select>
    </div>
    <hr>
	<h6 class="text-uppercase text-muted">Specifické filtry</h6>
	<div id="specificFilters"></div>

    <button id="resetFilters" class="btn btn-outline-secondary btn-sm w-100 mt-2">Reset</button>
  </div>
</aside>



    <!-- Mapa -->
    <main class="flex-grow-1 position-relative">
      <div id="map"></div>
    </main>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>

  window.APP = {
    api: {
      registry: "/armex/public/api/registry.php",
      data:     "/armex/public/api/data.php"
    }
  }
  </script>
  <script src="/armex/public/assets/js/app.js"></script>
</body>
</html>