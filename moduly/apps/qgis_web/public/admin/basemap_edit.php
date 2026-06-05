<?php
require_once __DIR__ . '/../../includes/admin_check.php';
require_once __DIR__ . '/../../includes/config_store.php';

$id = $_GET['id'] ?? null;
$rec = null;
if ($id) {
  $store = config_store();
  $rec = $store->getBasemap($id);
}
?>
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Admin – Podklad</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<div class="container py-4">
  <h1 class="h4 mb-3"><?= $id ? 'Upravit podklad' : 'Nový podklad' ?></h1>

  <form id="frmBasemap" class="card p-3">
    <div class="row g-2">
      <div class="col-md-4">
        <label class="form-label">ID</label>
        <input name="id" class="form-control" value="<?= htmlspecialchars($rec['id'] ?? '') ?>" <?= $id ? 'readonly' : '' ?> required>
      </div>
      <div class="col-md-4">
        <label class="form-label">Název</label>
        <input name="title" class="form-control" value="<?= htmlspecialchars($rec['title'] ?? '') ?>" required>
      </div>
      <div class="col-md-4">
        <label class="form-label">MaxZoom</label>
        <input name="maxZoom" type="number" class="form-control" value="<?= htmlspecialchars($rec['maxZoom'] ?? 22) ?>">
      </div>
    </div>

    <div class="row g-2 mt-2">
      <div class="col-md-8">
        <label class="form-label">URL (XYZ template)</label>
        <input name="url" class="form-control" value="<?= htmlspecialchars($rec['url'] ?? '') ?>" required>
      </div>
      <div class="col-md-4">
        <label class="form-label">Attribution</label>
        <input name="attribution" class="form-control" value="<?= htmlspecialchars($rec['attribution'] ?? '') ?>">
      </div>
    </div>

    <div class="mt-3 d-flex gap-2">
      <button type="button" class="btn btn-primary" onclick="basemapEditor.save()">Uložit</button>
      <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Zpět</button>
    </div>
  </form>
</div>

<script>
(() => {
  async function init(id = null) {
    // pokud otevřeno samostatně – data jsou už propsané z PHP
    // při modalovém použití by šlo fetchnout, kdyby bylo třeba
  }

  async function save() {
    const f = document.getElementById('frmBasemap');
    const fd = new FormData(f);
    const payload = {};
    fd.forEach((v,k)=>payload[k]=v);

    if(!payload.id || !payload.title) {
      alert('Vyplňte ID a Název');
      return;
    }

    const res = await fetch('api/save_basemap.php', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if(!res.ok) {
      alert('Uložení selhalo');
      return;
    }
    const out = await res.json().catch(()=>({success:false}));
    if(!out.success) {
      alert('Chyba: '+(out.message||'Uložení selhalo'));
      return;
    }

    if (typeof window.load === 'function') { try { window.load(); } catch(_){} }

    const modalEl = document.getElementById('basemapModal');
    if (modalEl && window.bootstrap?.Modal) {
      const inst = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
      inst.hide();
    }
  }

  // vystav do globálu stejně jako layerEditor
  if (!window.basemapEditor)// už existuje, neřeš
  { window.basemapEditor = { init, save, chg };}

  // pokud otevřeno samostatně
  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('frmBasemap')) init();
  });
})();
</script>
</body>
</html>
