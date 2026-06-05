<?php
require_once __DIR__ . '/../../config.php';
require_once __DIR__ . '/../../includes/db.php';

header('Content-Type: application/json; charset=utf-8');

if (!isset($_GET['id'])) {
    echo json_encode(["ok"=>false, "msg"=>"Missing layer id"]);
    exit;
}

$layerId = $_GET['id'];

// načteme vrstvu z configu
require_once __DIR__ . '/../../includes/config_store.php';
$store = config_store();
$layer = $store->getLayer($layerId);

if (!$layer || ($layer['type'] ?? '') !== 'sql') {
    echo json_encode(["ok"=>false, "msg"=>"Layer not found or not sql"]);
    exit;
}

// získáme SQL dotaz
$sql = $layer['sql'] ?? '';
if (!$sql) {
    echo json_encode(["ok"=>false, "msg"=>"Missing SQL query"]);
    exit;
}

// povolíme jen SELECT
if (!preg_match('/^\s*select/i', $sql)) {
    echo json_encode(["ok"=>false, "msg"=>"Only SELECT allowed"]);
    exit;
}

try {
    $stmt = db()->query($sql);
    $rows = $stmt->fetchAll();
} catch (Exception $e) {
    echo json_encode(["ok"=>false, "msg"=>$e->getMessage()]);
    exit;
}

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
    "type" => "FeatureCollection",
    "features" => $features
]);
?>