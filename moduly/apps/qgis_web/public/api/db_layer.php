<?php
require_once __DIR__ . "/../../config.php";
require_once __DIR__ . "/../../includes/db.php";

header('Content-Type: application/json; charset=utf-8');

$sql = 'SELECT fid, ST_AsGeoJSON(geometry) AS geom FROM "HASÍCÍ PŘÍSTROJE";';
$rows = db()->query($sql)->fetchAll();

$features = [];

foreach ($rows as $r) {
    $features[] = [
        "type" => "Feature",
        "geometry" => json_decode($r['geom'], true),
        "properties" => [
            "id" => $r['fid'],
        ]
    ];
}

echo json_encode([
    "type" => "FeatureCollection",
    "features" => $features
]);
?>