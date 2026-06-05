<?php
// public/api/data.php
require_once __DIR__ . '/../../includes/config_store.php';
require_once __DIR__ . '/../../includes/auth_check.php';
require_once __DIR__ . '/../../includes/db.php';

header('Content-Type: application/json; charset=utf-8');

try {
  $id = $_GET['layer'] ?? '';
  if ($id === '') {
    http_response_code(400);
    echo json_encode(['error'=>'missing_layer']); exit;
  }

  $store = config_store();
  $L = $store->getLayer($id);
  if (!$L) {
    http_response_code(404);
    echo json_encode(['error'=>'unknown_layer']); exit;
  }

  $source = $L['source'] ?? 'static';

  // ============================================
  // STATIC zdroj – načítá public/data/{soubor}
  // ============================================
  if ($source === 'static') {
    $fname = $L['staticData'] ?? '';
    $path  = __DIR__ . '/../data/' . $fname;

    $fc = ['type'=>'FeatureCollection','features'=>[]];
    if ($fname && is_file($path)) {
      $json = file_get_contents($path);
      $data = json_decode($json, true);
      if (is_array($data)) $fc = $data;
    }

    echo json_encode([
      'meta' => [
        'id'       => $L['id'],
        'title'    => $L['title'],
        'geomType' => $L['geomType'],
'priority' => $L['priority'] ?? 0
      ],
      'data' => $fc
    ], JSON_UNESCAPED_UNICODE);
    exit;
  }



  // ============================================
  // SQL zdroj – DOPLNĚNO
  // ============================================
  if ($source === 'sql') {

    $sql = $L['sql'] ?? '';

    if (!$sql) {
      echo json_encode([
        'error' => 'sql_missing',
        'message' => 'SQL query not set for this layer'
      ]);
      exit;
    }

    // bezpečnost – povolíme jen SELECT
    if (!preg_match('/^\s*select/i', $sql)) {
      echo json_encode([
        'error' => 'sql_forbidden',
        'message' => 'Only SELECT queries allowed'
      ]);
      exit;
    }

    try {
      $rows = db()->query($sql)->fetchAll();
    } catch (Throwable $e) {
      echo json_encode([
        'error' => 'sql_failed',
        'message' => $e->getMessage()
      ]);
      exit;
    }

    // převést řádky na GeoJSON
    $features = [];
    foreach ($rows as $r) {
      if (!isset($r['geom'])) continue;

      $features[] = [
        "type" => "Feature",
        "geometry" => json_decode($r['geom'], true),
        "properties" => array_diff_key($r, ['geom'=>1])
      ];
    }

    echo json_encode([
      'meta' => [
        'id'       => $L['id'],
        'title'    => $L['title'],
        'geomType' => $L['geomType'],
'priority' => $L['priority'] ?? 0

      ],
      'data' => [
        "type" => "FeatureCollection",
        "features" => $features
      ]
    ], JSON_UNESCAPED_UNICODE);

    exit;
  }



  // ============================================
  // Ostatní zdroje (nenasazeno)
  // ============================================
  echo json_encode([
    'meta' => [
      'id'       => $L['id'],
      'title'    => $L['title'],
      'geomType' => $L['geomType']
    ],
    'data' => [
      'type' => 'FeatureCollection',
      'features' => []
    ]
  ], JSON_UNESCAPED_UNICODE);

} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['error'=>'data_failed','message'=>$e->getMessage()]);
}
?>
