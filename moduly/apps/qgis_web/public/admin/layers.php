<?php require_once __DIR__ . '/../../includes/admin_check.php'; ?>
<!doctype html><html lang="cs"><head>
<meta charset="utf-8"><title>Admin – Vrstvy</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</head><body>
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <button class="btn btn-primary" onclick="openLayerEdit()">+ Nová vrstva</button>
  </div>
  <table class="table table-sm align-middle" id="tbl"></table>
</div>

<!-- Modal -->
<div class="modal fade" id="layerModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-xl modal-dialog-scrollable">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Vrstva</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Zavřít"></button>
      </div>
      <div class="modal-body" id="layerModalContent">Načítám…</div>
    </div>
  </div>
</div>

<script>
async function load() {
  const res = await fetch('api/list_layers.php');
  const layers = await res.json();
  const tbl = document.getElementById('tbl');
  tbl.innerHTML =
    '<tr><th>ID</th><th>Název</th><th>Geometrie</th><th>Zdroj</th><th class="text-end">Akce</th></tr>' +
    layers.map(L => `
      <tr>
        <td>${L.id}</td>
        <td>${L.title}</td>
        <td>${L.geomType}</td>
        <td>${L.source}</td>
        <td class="text-end">
          <button class="btn btn-sm btn-outline-primary" onclick="openLayerEdit('${L.id}')">Edit</button>
          <button class="btn btn-sm btn-outline-danger" onclick="delL('${L.id}')">Smazat</button>
        </td>
      </tr>`).join('');
}

async function delL(id){
  if(!confirm('Smazat vrstvu ' + id + '?')) return;
  await fetch('api/delete_layer.php?id='+encodeURIComponent(id), {method:'POST'});
  load();
}

async function openLayerEdit(id = null) {
  const resp = await fetch('layer_edit.php');
  const html = await resp.text();

  const box = document.getElementById('layerModalContent');
  box.innerHTML = html;

  // >>> SPUSŤ <script> tagy z načteného HTML (stejná finta jako v index.php)
  box.querySelectorAll('script').forEach(oldScript => {
    const s = document.createElement('script');
    if (oldScript.src) {
      s.src = oldScript.src;
    } else {
      s.textContent = oldScript.textContent;
    }
    document.body.appendChild(s);
  });
  // <<<

  const modal = new bootstrap.Modal(document.getElementById('layerModal'));
  modal.show();

  // Teď už je window.layerEditor jistě definovaný a init je async:
  if (window.layerEditor && typeof window.layerEditor.init === 'function') {
    window.layerEditor.init(id);
  }
}


// Zpřístupni load(), aby ho mohl po uložení zavolat editor:
window.load = load;

load();
</script>
</body></html>
