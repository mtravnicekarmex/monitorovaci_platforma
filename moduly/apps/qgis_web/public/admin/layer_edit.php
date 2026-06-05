<?php require_once __DIR__ . '/../../includes/admin_check.php'; ?>
<!doctype html><html lang="cs"><head>
<meta charset="utf-8"><title>Admin – Vrstva</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head><body>
<div class="container py-4">
  <h1 class="h4 mb-3">Vrstva</h1>

  <form id="frmLayer" class="card p-3">
    <div class="row g-2">
      <div class="col-md-4">
        <label class="form-label">ID</label>
        <input name="id" class="form-control" required>
      </div>
      <div class="col-md-4">
        <label class="form-label">Název</label>
        <input name="title" class="form-control" required>
      </div>
	  
	  <div class="col-md-4">
  <label class="form-label">Barva</label>
  <input name="color" type="color" class="form-control form-control-color">
</div>

      <div class="col-md-4">
        <label class="form-label">Geometrie</label>
        <select name="geomType" class="form-select">
          <option>Point</option><option>Polygon</option><option>Linie</option>
        </select>
      </div>
    </div>

    <div class="row g-2 mt-2">

<div class="col-md-4">
  <label class="form-label">Priorita vykreslení</label>
  <input name="priority" type="number" class="form-control" placeholder="0 = nejnižší">
</div>

      <div class="col-md-4">
        <label class="form-label">Zdroj</label>
        <select name="source" class="form-select">
          <option>static</option><option>sql</option>
        </select>
      </div>
      <div class="col-md-8">
        <label class="form-label">Soubor (pro static)</label>
        <input name="staticData" class="form-control" placeholder="např. buildings.json">

<div class="mt-2">
  <label class="form-label">SQL dotaz (pro source = sql)</label>
  <textarea name="sql" class="form-control" rows="4"
    placeholder="SELECT id, ST_AsGeoJSON(geom) AS geom FROM public.tabulka"></textarea>
</div>
      </div>
    </div>

    <hr class="my-3">
    <div class="d-flex justify-content-between align-items-center">
      <h6 class="mb-0">Specifické filtry</h6>
      <button class="btn btn-sm btn-outline-primary" type="button" onclick="layerEditor.addFilter()">+ Přidat</button>
    </div>
    <div id="specBox" class="mt-2"></div>

    <div class="mt-3 d-flex gap-2">
      <button class="btn btn-primary" type="button" onclick="layerEditor.save()">Uložit</button>
      <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Zpět</button>
    </div>
  </form>
</div>

<!-- Bootstrap JS NEVKLÁDEJ podruhé; je už na rodičovské stránce -->

<script>
(() => {
  const state = { specificFilters: [] };

  function chg(i,k,v){ state.specificFilters[i][k]=v; }
  function rem(i){ state.specificFilters.splice(i,1); renderSpecFilters(); }
  function addFilter(){
    state.specificFilters.push({type:'checkbox', id:'', label:'', property:'', predicate:'', values:[]});
    renderSpecFilters();
    requestAnimationFrame(()=>{
      const acc = document.getElementById('collapse-'+(state.specificFilters.length-1));
      if (acc && window.bootstrap?.Collapse) new bootstrap.Collapse(acc, {toggle:true});
    });
  }

  function renderSpecFilters(){
    const box = document.getElementById('specBox');
    box.innerHTML = `
      <div class="accordion" id="filtersAccordion">
        ${state.specificFilters.map((f,i)=>`
          <div class="accordion-item mb-2">
            <h2 class="accordion-header" id="heading-${i}">
              <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${i}">
                ${f.label ? f.label : ('Filtr ' + (i+1))} <span class="text-muted small ms-1">(${f.type||'?'})</span>
              </button>
            </h2>
            <div id="collapse-${i}" class="accordion-collapse collapse" data-bs-parent="#filtersAccordion">
              <div class="accordion-body">
                <div class="row g-2">
                  <div class="col-md-3">
                    <label class="form-label">Typ <span data-bs-toggle="tooltip" title="checkbox nebo select">❔</span></label>
                    <select class="form-select form-select-sm" onchange="layerEditor.chg(${i},'type',this.value)">
                      <option ${f.type==='checkbox'?'selected':''}>checkbox</option>
                      <option ${f.type==='select'?'selected':''}>select</option>
                    </select>
                  </div>
                  <div class="col-md-3">
                    <label class="form-label">ID <span data-bs-toggle="tooltip" title="Unikátní název filtru, např. expired">❔</span></label>
                    <input class="form-control form-control-sm" value="${f.id||''}" onchange="layerEditor.chg(${i},'id',this.value)">
                  </div>
                  <div class="col-md-3">
                    <label class="form-label">Label <span data-bs-toggle="tooltip" title="Text zobrazený v dashboardu">❔</span></label>
                    <input class="form-control form-control-sm" value="${f.label||''}" onchange="layerEditor.chg(${i},'label',this.value)">
                  </div>
                  <div class="col-md-3">
                    <label class="form-label">Property <span data-bs-toggle="tooltip" title="Atribut z dat (pro select)">❔</span></label>
                    <input class="form-control form-control-sm" value="${f.property||''}" onchange="layerEditor.chg(${i},'property',this.value)">
                  </div>
                </div>

                <div class="mt-2">
                  <label class="form-label">Predicate <span data-bs-toggle="tooltip" title="Např. empty(vyuziti) nebo date(revize_exp) < today()">❔</span></label>
                  <input class="form-control form-control-sm" value="${f.predicate||''}" onchange="layerEditor.chg(${i},'predicate',this.value)">
                </div>

                <div class="mt-2">
                  <label class="form-label">Hodnoty pro select <span data-bs-toggle="tooltip" title="Oddělené čárkou. Pokud prázdné, vygenerují se automaticky z dat.">❔</span></label>
                  <input class="form-control form-control-sm" value="${(f.values||[]).join(',')}"
                        onchange="layerEditor.chg(${i},'values',this.value.split(',').map(v=>v.trim()).filter(Boolean))">
                </div>

                <div class="text-end mt-2">
                  <button class="btn btn-sm btn-outline-danger" type="button" onclick="layerEditor.rem(${i})">Odstranit</button>
                </div>
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    `;
    if (window.bootstrap?.Tooltip) {
      document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => new bootstrap.Tooltip(el));
    }
  }

  // přepínání UI static / sql
  function updateSourceUI() {
    const f = document.getElementById('frmLayer');
    if (!f) return;
    const src = f.source.value;

    const staticLabel = f.staticData ? f.staticData.previousElementSibling : null;
    const staticInput = f.staticData || null;
    const sqlWrap = f.sql ? f.sql.closest('.mt-2') : null;

    if (staticLabel) staticLabel.style.display = (src === 'static') ? 'block' : 'none';
    if (staticInput) staticInput.style.display = (src === 'static') ? 'block' : 'none';
    if (sqlWrap) sqlWrap.style.display = (src === 'sql') ? 'block' : 'none';
  }

  async function init(layerId = null){
    const f = document.getElementById('frmLayer');
    if (!f) return;

    if (layerId) {
      const res = await fetch('api/get_layer.php?id=' + encodeURIComponent(layerId));
      if (!res.ok) { alert('Načtení vrstvy selhalo'); return; }
      const L = await res.json();
      f.id.value = L.id; 
      f.id.readOnly = true;
      f.title.value = L.title || '';
      f.color.value = L.color || '#1f6feb'; 
      f.geomType.value = L.geomType || 'Point';
      f.source.value = L.source || 'static';
      f.staticData.value = L.staticData || '';
      f.sql.value = L.sql || '';
      state.specificFilters = L.specificFilters || [];
f.priority.value = L.priority ?? 0;
    } else {
      f.id.readOnly = false;
      f.id.value = ''; 
      f.title.value = ''; 
      f.staticData.value = ''; 
      f.sql.value = '';
      f.color.value = '#1f6feb';
      f.geomType.value = 'Point';
      f.source.value = 'static';
f.priority.value = 0;
      state.specificFilters = [];
    }

    // event handler na přepnutí zdroje
    f.source.addEventListener('change', updateSourceUI);
    updateSourceUI();

    renderSpecFilters();
  }

  async function save(){
    const f = document.getElementById('frmLayer');
    const payload = {
      id: (f.id.value||'').trim(),
      title: (f.title.value||'').trim(),
      geomType: f.geomType.value,
      source: f.source.value,
      color: f.color.value,
      staticData: (f.staticData.value||'').trim() || null,
      sql: (f.sql.value||'').trim() || null,
      specificFilters: state.specificFilters,
priority: Number(f.priority.value ?? 0)
    };
    if (!payload.id || !payload.title) { alert('Vyplň ID a Název'); return; }

    const res = await fetch('api/save_layer.php', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if (!res.ok) { alert('Uložení selhalo'); return; }

    if (typeof window.load === 'function') { try { window.load(); } catch(_){} }
    if (document.activeElement) document.activeElement.blur();
    const modalEl = document.getElementById('layerModal');
    if (modalEl && window.bootstrap?.Modal) {
      const inst = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
      inst.hide();
    }
  }

  window.layerEditor = { init, save, addFilter, rem, chg };

  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('frmLayer')) init();
  });
})();
</script>

</body></html>
