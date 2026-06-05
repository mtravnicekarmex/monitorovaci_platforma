(function () {
  const layersList = document.getElementById('layersList');
  const resetFiltersBtn = document.getElementById('resetFilters');
  const specificFiltersBox = document.getElementById('specificFilters');

  const fBudova = document.getElementById('filterBudova');
  const fPatro  = document.getElementById('filterPatro');

  const specificValues = {};    
  const registry = [];          
  const layerObjs = {};         
  const activeLayers = new Set();

  const map = L.map('map', { center: [50.77,14.23], zoom: 18, maxZoom: 22 });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:22}).addTo(map);

  function makeLayer(def) {
  if (def.geomType === 'Point') {
    return L.geoJSON(null, {
      pointToLayer: (f, latlng) => L.circleMarker(latlng, {
        radius: 6,
        weight: 1,
        color: def.color || '#333',
        fillColor: def.color || '#ff8a00',
        fillOpacity: 0.9
      }),
      onEachFeature: (f, l) => l.bindPopup(renderProps(f.properties))
    });
  }

  // Polygon nebo LineString
  return L.geoJSON(null, {
    style: (f) => ({
      color: def.color || '#1f6feb',
      weight: 2,
      fillColor: def.color || '#9ecbff',
      fillOpacity: 0.3
    }),
    onEachFeature: (f, l) => l.bindPopup(renderProps(f.properties))
  });
}


  function renderProps(p) {
  return `<div>${
    Object.entries(p||{})
      .filter(([k,_]) => k.toLowerCase() !== "geometry")   // <- VYNECHÁ geometry
      .map(([k,v]) => `<div><b>${k}</b>: ${v ?? '-'}</div>`)
      .join('')
  }</div>`;
}


  function setLayerCount(id,n){
    const el=document.querySelector(`.layer-count[data-count-for="${id}"]`);
    if(el) el.textContent=`(${n})`;
  }

  // UI pro zapínání vrstev
  function buildLayersUI() {
    layersList.innerHTML='';
    registry.forEach(def=>{
      const id=`layer-${def.id}`;
      const row=document.createElement('div');
      row.className='form-check mb-2';
      row.innerHTML=`
        <input class="form-check-input layer-toggle" type="checkbox" value="${def.id}" id="${id}" checked>
        <label class="form-check-label d-flex justify-content-between" for="${id}">
          <span>${def.title} <span class="text-muted layer-count" data-count-for="${def.id}">(0)</span></span>
        </label>`;
      layersList.appendChild(row);
    });
    layersList.querySelectorAll('.layer-toggle').forEach(cb=>{
      cb.addEventListener('change',()=>{
        const id=cb.value;
        if(cb.checked){
          activeLayers.add(id);
          layerObjs[id]?.layer.addTo(map);
        } else {
          activeLayers.delete(id);
          if(layerObjs[id]) map.removeLayer(layerObjs[id].layer);
        }
        buildSpecificFiltersUI();
        refreshFilters();
        applyFilters();
      });
    });
  }

  // UI pro specifické filtry
  function buildSpecificFiltersUI() {
  specificFiltersBox.innerHTML='';
  registry.forEach(def=>{
    const spec=def.specificFilters||[];
    if(!spec.length) return;
    const wrap=document.createElement('div');
    wrap.className='mb-3';
    wrap.innerHTML=`<div class="small fw-bold mb-1">${def.title}</div>`;
    specificFiltersBox.appendChild(wrap);

    specificValues[def.id]=specificValues[def.id]||{};

    spec.forEach(f=>{
      const domId=`sf-${def.id}-${f.id}`;

      if(f.type==='checkbox'){
        const div=document.createElement('div');
        div.className='form-check mb-1';
        div.innerHTML=`
          <input class="form-check-input" type="checkbox" id="${domId}">
          <label class="form-check-label" for="${domId}">${f.label}</label>`;
        wrap.appendChild(div);
        div.querySelector('input').addEventListener('change',e=>{
          specificValues[def.id][f.id]=e.target.checked;
          applyFilters();
        });
      }

      if(f.type==='select'){
        const div=document.createElement('div');
        div.className='mb-2';
        div.innerHTML=`
          <label class="form-label small" for="${domId}">${f.label}</label>
          <select class="form-select form-select-sm" id="${domId}">
            <option value="">– vše –</option>
          </select>`;
        wrap.appendChild(div);
        div.querySelector('select').addEventListener('change',e=>{
          specificValues[def.id][f.id]=e.target.value||null;
          applyFilters();
        });
      }
    });
  });

  // hned doplň hodnoty do všech selectů podle aktuálních dat
  refreshFilters();
}

function getBudova(p) {
  if (!p) return null;

  // přesné názvy
  if (p.budova) return p.budova;
  if (p.budova_id) return p.budova_id;
  if (p.id_budovy) return p.id_budovy;
  if (p.id_budova) return p.id_budova;

  // fallback – case-insensitive
  for (const k of Object.keys(p)) {
    const lk = k.toLowerCase();
    if (lk.includes("budova")) {
      const v = p[k];
      if (v !== null && v !== "") return v;
    }
  }

  return null;
}

function getPatro(p) {
  if (!p) return null;

  // přesné názvy
  if (p.patro !== undefined && p.patro !== null && p.patro !== "") return p.patro;
  if (p.level !== undefined && p.level !== null && p.level !== "") return p.level;
  if (p.floor !== undefined && p.floor !== null && p.floor !== "") return p.floor;

  // fallback – case-insensitive
  for (const k of Object.keys(p)) {
    const lk = k.toLowerCase();
    if (lk === "patro" || lk === "level" || lk === "floor") {
      const v = p[k];
      if (v !== null && v !== "") return v;
    }
  }

  return null;
}


  // doplnění hodnot do selectů (včetně pevného "budova" a "patro")
function refreshFilters() {
  const budovy = new Set();
  const patra  = new Set();

  activeLayers.forEach(id => {
    const fc = layerObjs[id]?.data || {features: []};

    (fc.features || []).forEach(f => {
      const p = f.properties || {};

      // ====== Sjednocené názvy pro BUDOVU ======
      const valBud = getBudova(p);
if (valBud !== null && valBud !== "") budovy.add(String(valBud));

const valPat = getPatro(p);
if (valPat !== null && valPat !== "") patra.add(String(valPat));
    });
  });

  // Seřazené doplňování selectů
  const fillSelect = (sel, set, placeholder) => {
    if (!sel) return;

    const items = Array.from(set).sort((a, b) => {
      const na = Number(a), nb = Number(b);
      if (!isNaN(na) && !isNaN(nb)) return na - nb;
      return String(a).localeCompare(String(b), 'cs');
    });

    const prev = sel.value;
    sel.innerHTML = `<option value="">${placeholder}</option>`;

    items.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });

    if (items.includes(prev)) {
      sel.value = prev;
    }
  };

  fillSelect(fBudova, budovy, '– všechny –');
  fillSelect(fPatro, patra,   '– všechna –');

  // ===== SPECIFICKÉ SELECT FILTRY =====
  registry.forEach(def => {
    const spec = def.specificFilters || [];

    spec.forEach(f => {
      if (f.type !== 'select') return;

      const sel = document.getElementById(`sf-${def.id}-${f.id}`);
      if (!sel) return;

      let values = [];

      if (f.values && f.values.length) {
        // pevně zadané hodnoty
        values = f.values;
      } else {
        // dynamické načtení hodnot z dat
        const fc = layerObjs[def.id]?.data || {features: []};
        const set = new Set();

        (fc.features || []).forEach(feat => {
          const p = feat.properties || {};

          // sjednocené sloupce pro specifické filtry
          const val =
            p[f.property] ??
            p[f.property + "_id"] ??
            p[f.property + "_code"] ??
            null;

          if (val !== null && val !== '') {
            set.add(String(val));
          }
        });

        values = [...set];
      }

      // seřadit
      values.sort((a, b) => String(a).localeCompare(String(b), 'cs'));

      // znovu vytvořit select
      const prev = sel.value;
      sel.innerHTML = `<option value="">– vše –</option>`;

      values.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        sel.appendChild(opt);
      });

      if (values.includes(prev)) sel.value = prev;
    });
  });
}



  function checkSpecificFilters(layerId,props){
    const filters=registry.find(d=>d.id===layerId)?.specificFilters||[];
    const values=specificValues[layerId]||{};
    for(const f of filters){
      const val=values[f.id];
      if(f.type==='checkbox' && val){
        if(f.predicate && !evalPredicate(f.predicate,props)) return false;
      }
      if(f.type==='select' && val){
        if(f.property && String(props[f.property]??'')!==String(val)) return false;
      }
    }
    return true;
  }

  function evalPredicate(expr,props){
    if(!expr) return true;
    if(expr.startsWith('empty(')){
      const field=expr.match(/^empty\((.*)\)$/)[1];
      return !props[field] || String(props[field]).trim()==='';
    }
    return true;
  }

let basemapLayers = {};   // id → L.tileLayer
let currentBasemap = null;

function addBasemapControl(basemaps) {
  // vytvoř control v pravém dolním rohu
  const control = L.control({position: 'bottomright'});
  control.onAdd = function() {
    const div = L.DomUtil.create('div', 'leaflet-bar p-1 bg-white');
    const sel = L.DomUtil.create('select', '', div);
    sel.className = 'form-select form-select-sm';

    basemaps.forEach((b,i) => {
      const opt = document.createElement('option');
      opt.value = b.id;
      opt.textContent = b.title;
      sel.appendChild(opt);

      // připrav samotnou L.tileLayer
      basemapLayers[b.id] = L.tileLayer(b.url, {
        maxZoom: b.maxZoom || 22,
        attribution: b.attribution || ''
      });

      // první přidej rovnou do mapy
      if (i === 0) {
        currentBasemap = basemapLayers[b.id];
        currentBasemap.addTo(map);
        sel.value = b.id;
      }
    });

    sel.addEventListener('change', () => {
      if (currentBasemap) map.removeLayer(currentBasemap);
      const id = sel.value;
      currentBasemap = basemapLayers[id];
      if (currentBasemap) currentBasemap.addTo(map);
    });

    // zabrání scroll zoomu při hoveru na selectu
    L.DomEvent.disableClickPropagation(div);
    return div;
  };
  control.addTo(map);
}

  function applyFilters(){
    const bud=fBudova.value;
    const pat=fPatro.value;

    const okBudAny = (p) => {
  if (!bud) return true;
  const v = getBudova(p);
  return v != null && String(v) === String(bud);
};

    const okPat   =p=>!pat || String(p.patro)===pat;

    const counts={};
    registry.forEach(layer=>{
      const feats=(layerObjs[layer.id]?.data?.features)||[];
      const filtered=feats.filter(f=>{
        const p=f.properties||{};
        if(!okBudAny(p)||!okPat(p)) return false;
        return checkSpecificFilters(layer.id,p);
      });
      const l=layerObjs[layer.id]?.layer;
      if(l){
        l.clearLayers();
        l.addData({type:'FeatureCollection',features:filtered});
        counts[layer.id]=activeLayers.has(layer.id)?filtered.length:0;
      }
    });
    Object.entries(counts).forEach(([id,n])=>setLayerCount(id,n));
    setTimeout(()=>{ map.invalidateSize(); },200);
  }

  // Eventy – okamžitá aplikace filtrů
  fBudova.addEventListener('change',applyFilters);
  fPatro.addEventListener('change',applyFilters);

  resetFiltersBtn.addEventListener('click',()=>{
    fBudova.value=''; fPatro.value='';
    Object.keys(specificValues).forEach(lid=>{
      Object.keys(specificValues[lid]).forEach(fid=>specificValues[lid][fid]=null);
    });
    buildSpecificFiltersUI();
    refreshFilters();
    applyFilters();
  });

  // Init
  fetch(window.APP.api.registry)
  .then(r => r.json())
  .then(data => {
    const layers = data.layers || [];      // vytáhnout pole vrstev
    const basemaps = data.basemaps || [];  // uložit si podklady, můžeš použít do <select>

 if (basemaps.length) {
    addBasemapControl(basemaps);
  }
    layers
  .map(d => ({
    ...d,
    priority: d.priority ?? d.meta?.priority ?? 0
  }))
  .sort((a,b) => a.priority - b.priority)
  .forEach(d => registry.push(d));


    buildLayersUI();

    return Promise.all(registry.map(def => {
      return fetch(`${window.APP.api.data}?layer=${def.id}`)
        .then(r => r.json())
        .then(resp => {
          const layer = makeLayer(def);
          layer.addData(resp.data);
          layer.addTo(map);
          layerObjs[def.id] = { layer, data: resp.data };
          activeLayers.add(def.id);
        });
    }));
  }).then(()=>{
    buildSpecificFiltersUI();
    refreshFilters();
    applyFilters();

    // Fit na extent všech vrstev
    let bounds=null;
    Object.values(layerObjs).forEach(o=>{
      try{
        const b=o.layer.getBounds();
        if(b.isValid()) bounds=bounds?bounds.extend(b):b;
      }catch(_){}
    });
    if(bounds) map.fitBounds(bounds,{padding:[20,20]});
  });
})();
