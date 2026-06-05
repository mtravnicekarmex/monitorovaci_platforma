<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Admin – Mapové podklady</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <button class="btn btn-primary" onclick="window.basemapEditor.open()">+ Nový podklad</button>
  </div>
  <table class="table table-sm align-middle" id="tbl"></table>
</div>

<!-- Modal -->
<div class="modal fade" id="basemapModal" tabindex="-1">
  <div class="modal-dialog modal-lg modal-dialog-scrollable">
    <div class="modal-content">
      <div class="modal-body">
        <form id="frmBasemap">
          <div class="mb-2">
            <label class="form-label">ID</label>
            <input class="form-control" name="id" required>
          </div>
          <div class="mb-2">
            <label class="form-label">Název</label>
            <input class="form-control" name="title" required>
          </div>
          <div class="mb-2">
            <label class="form-label">URL (XYZ)</label>
            <input class="form-control" name="url" required>
          </div>
          <div class="mb-2">
            <label class="form-label">Attribution</label>
            <input class="form-control" name="attribution">
          </div>
          <div class="mb-2">
            <label class="form-label">MaxZoom</label>
            <input class="form-control" name="maxZoom" type="number" value="22">
          </div>
        </form>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Zpět</button>
        <button type="button" class="btn btn-primary" onclick="window.basemapEditor.save()">Uložit</button>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
// Zajistí, že není redeklarace při opakovaném načtení
window.basemapEditor = {
  currentId: null,
  async load() {
    const res = await fetch('api/list_basemaps.php');
    const maps = await res.json();
    const tbl = document.getElementById('tbl');
    tbl.innerHTML = '<tr><th>ID</th><th>Název</th><th>URL</th><th>MaxZoom</th><th></th></tr>' +
      maps.map(m => `<tr>
        <td>${m.id}</td><td>${m.title}</td><td>${m.url}</td><td>${m.maxZoom||''}</td>
        <td class="text-end">
          <button class="btn btn-sm btn-outline-primary" onclick="window.basemapEditor.open('${m.id}')">Edit</button>
          <button class="btn btn-sm btn-outline-danger" onclick="window.basemapEditor.del('${m.id}')">Smazat</button>
        </td>
      </tr>`).join('');
  },
  async open(id = null) {
    this.currentId = id;
    const f = document.getElementById('frmBasemap');
    f.reset();
    if (id) {
      const res = await fetch('api/get_basemap.php?id='+encodeURIComponent(id));
      const rec = await res.json();
      f.id.value = rec.id;
      f.id.readOnly = true;
      f.title.value = rec.title||'';
      f.url.value = rec.url||'';
      f.attribution.value = rec.attribution||'';
      f.maxZoom.value = rec.maxZoom||22;
    } else {
      f.id.readOnly = false;
    }
    new bootstrap.Modal(document.getElementById('basemapModal')).show();
  },
  async save() {
    const f = document.getElementById('frmBasemap');
    const payload = {
      id: f.id.value.trim(),
      title: f.title.value.trim(),
      url: f.url.value.trim(),
      attribution: f.attribution.value.trim(),
      maxZoom: Number(f.maxZoom.value)||22
    };
    const res = await fetch('api/save_basemap.php', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if (!res.ok) { alert('Uložení selhalo'); return; }
    bootstrap.Modal.getInstance(document.getElementById('basemapModal')).hide();
    this.load();
  },
  async del(id) {
    if (!confirm('Smazat podklad '+id+'?')) return;
    await fetch('api/delete_basemap.php', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id})
    });
    this.load();
  }
};
window.basemapEditor.load();
</script>
</body>
</html>
