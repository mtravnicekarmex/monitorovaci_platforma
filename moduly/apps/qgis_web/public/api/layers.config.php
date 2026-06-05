<?php
// Centrální registr vrstev – snadné přidání dalších (např. "chairs")
return [
  // BUDOVY
  'buildings' => [
    'id'        => 'buildings',
    'title'     => 'Budovy',
    'geomType'  => 'Polygon',
    'source'    => 'static',      // 'static' | 'sql'
    'filters'   => ['id_budovy','patro','typ'], // 'typ' = určení/využití
	'specificFilters' => [
    // příklad Select podle určení (optional)
    [
      'id' => 'urceni',
      'type' => 'select',   // 'checkbox' | 'select'
      'label' => 'Určení',
      'property' => 'urceni', // z properties
      'values' => null       // null = vygenerovat z dat; nebo ['administrativa','sklad']
    ],
  ],
    'static_loader' => function () {
      return [
        'type'=>'FeatureCollection','features'=>[
          [
            'type'=>'Feature',
            'properties'=>['id_budovy'=>'B1','nazev'=>'Administrativní budova','urceni'=>'administrativa','typ'=>'administrativa'],
            'geometry'=>['type'=>'Polygon','coordinates'=>[[[14.23535,50.77757],[14.23565,50.77757],[14.23565,50.77773],[14.23535,50.77773],[14.23535,50.77757]]]]
          ],
          [
            'type'=>'Feature',
            'properties'=>['id_budovy'=>'B2','nazev'=>'Hlavní sklad','urceni'=>'sklad','typ'=>'sklad'],
            'geometry'=>['type'=>'Polygon','coordinates'=>[[[14.23595,50.77748],[14.23625,50.77748],[14.23625,50.77762],[14.23595,50.77762],[14.23595,50.77748]]]]
          ]
        ]
      ];
    },
  ],

  // MÍSTNOSTI
  'rooms' => [
    'id'        => 'rooms',
    'title'     => 'Místnosti',
    'geomType'  => 'Polygon',
    'source'    => 'static',
    'filters'   => ['budova_id','patro','typ'], // typ = vyuziti
	'specificFilters' => [
    [
      'id' => 'unused',
      'type' => 'checkbox',
      'label' => 'Bez využití',
      // evaluator na FE: "vyuziti" je prázdné/null → true
      'predicate' => 'empty(vyuziti)'
    ],
  ],
    'static_loader' => function () {
      return [
        'type'=>'FeatureCollection','features'=>[
          ['type'=>'Feature','properties'=>['id_mistnosti'=>'B1-101','budova_id'=>'B1','patro'=>0,'vyuziti'=>'kancelar','typ'=>'kancelar'],
           'geometry'=>['type'=>'Polygon','coordinates'=>[[[14.23537,50.77759],[14.23550,50.77759],[14.23550,50.77767],[14.23537,50.77767],[14.23537,50.77759]]]]],
          ['type'=>'Feature','properties'=>['id_mistnosti'=>'B1-102','budova_id'=>'B1','patro'=>0,'vyuziti'=>'zasedacka','typ'=>'zasedacka'],
           'geometry'=>['type'=>'Polygon','coordinates'=>[[[14.23552,50.77759],[14.23563,50.77759],[14.23563,50.77767],[14.23552,50.77767],[14.23552,50.77759]]]]],
          ['type'=>'Feature','properties'=>['id_mistnosti'=>'B1-201','budova_id'=>'B1','patro'=>1,'vyuziti'=>'serverovna','typ'=>'serverovna'],
           'geometry'=>['type'=>'Polygon','coordinates'=>[[[14.23545,50.77769],[14.23560,50.77769],[14.23560,50.77772],[14.23545,50.77772],[14.23545,50.77769]]]]],
          ['type'=>'Feature','properties'=>['id_mistnosti'=>'B2-B01','budova_id'=>'B2','patro'=>-1,'vyuziti'=>'sklad','typ'=>'sklad'],
           'geometry'=>['type'=>'Polygon','coordinates'=>[[[14.23598,50.77750],[14.23612,50.77750],[14.23612,50.77758],[14.23598,50.77758],[14.23598,50.77750]]]]],
          ['type'=>'Feature','properties'=>['id_mistnosti'=>'B2-001','budova_id'=>'B2','patro'=>0,'vyuziti'=>'expedice','typ'=>'expedice'],
           'geometry'=>['type'=>'Polygon','coordinates'=>[[[14.23614,50.77750],[14.23623,50.77750],[14.23623,50.77758],[14.23614,50.77758],[14.23614,50.77750]]]]],
        ]
      ];
    },
  ],

  // HASIČÁKY
  'extinguishers' => [
    'id'        => 'extinguishers',
    'title'     => 'Hasičáky',
    'geomType'  => 'Point',
    'source'    => 'static',
    'filters'   => ['budova_id','mistnost_id','patro','revize_exp'],
	'specificFilters' => [
    [
      'id' => 'expired',
      'type' => 'checkbox',
      'label' => 'Po expiraci',
      // evaluator na FE: datum revize_exp < dnes
      'predicate' => 'date(revize_exp) < today()'
    ],
  ],
    'static_loader' => function () {
      return [
        'type'=>'FeatureCollection','features'=>[
          ['type'=>'Feature','properties'=>['id'=>'E-001','budova_id'=>'B1','mistnost_id'=>'B1-101','patro'=>0,'revize_exp'=>'2026-03-31'],'geometry'=>['type'=>'Point','coordinates'=>[14.23543,50.77763]]],
          ['type'=>'Feature','properties'=>['id'=>'E-002','budova_id'=>'B1','mistnost_id'=>'B1-102','patro'=>0,'revize_exp'=>'2025-12-31'],'geometry'=>['type'=>'Point','coordinates'=>[14.23558,50.77763]]],
          ['type'=>'Feature','properties'=>['id'=>'E-003','budova_id'=>'B1','mistnost_id'=>'B1-201','patro'=>1,'revize_exp'=>'2026-06-30'],'geometry'=>['type'=>'Point','coordinates'=>[14.23552,50.77771]]],
          ['type'=>'Feature','properties'=>['id'=>'E-101','budova_id'=>'B2','mistnost_id'=>'B2-B01','patro'=>-1,'revize_exp'=>'2025-11-30'],'geometry'=>['type'=>'Point','coordinates'=>[14.23605,50.77754]]],
          ['type'=>'Feature','properties'=>['id'=>'E-102','budova_id'=>'B2','mistnost_id'=>'B2-001','patro'=>0,'revize_exp'=>'2026-01-31'],'geometry'=>['type'=>'Point','coordinates'=>[14.23619,50.77754]]],
        ]
      ];
    },
  ],

  // ŽIDLE
  'chairs' => [
    'id'        => 'chairs',
    'title'     => 'Židle',
    'geomType'  => 'Point',
    'source'    => 'static',
    'filters'   => ['budova_id','mistnost_id','patro','typ'],
    'static_loader' => function () {
      return [
        'type'=>'FeatureCollection','features'=>[
          [
            'type'=>'Feature',
            'properties'=>['id'=>'CH-001','budova_id'=>'B1','mistnost_id'=>'B1-101','patro'=>0,'typ'=>'konferencni'],
            'geometry'=>['type'=>'Point','coordinates'=>[14.23546,50.77763]]
          ],
          [
            'type'=>'Feature',
            'properties'=>['id'=>'CH-002','budova_id'=>'B1','mistnost_id'=>'B1-102','patro'=>0,'typ'=>'zasedaci'],
            'geometry'=>['type'=>'Point','coordinates'=>[14.23559,50.77762]]
          ],
          [
            'type'=>'Feature',
            'properties'=>['id'=>'CH-003','budova_id'=>'B2','mistnost_id'=>'B2-001','patro'=>0,'typ'=>'pracovni'],
            'geometry'=>['type'=>'Point','coordinates'=>[14.23618,50.77756]]
          ],
        ]
      ];
    },
  ],
];
