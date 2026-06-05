<?php
ini_set('display_errors',1);
error_reporting(E_ALL);

require_once __DIR__ . '/../../includes/auth_check.php';
require_once __DIR__ . '/../../includes/config_store.php';

header('Content-Type: application/json; charset=utf-8');

try {
  $store = config_store();
  $layers = $store->listLayers();
  $basemaps = $store->listBasemaps(); // ⬅️ přidej do config_store / DB

  $out = [
    "layers" => array_map(function($L){
      return [
        "id"       => $L['id'],
        "title"    => $L['title'],
        "geomType" => $L['geomType'],
"priority" => $L['priority'],
        "color"    => $L['color'] ?? null,
        "specificFilters" => $L['specificFilters'] ?? []
      ];
    }, $layers),
    "basemaps" => array_map(function($B){
      return [
        "id"    => $B['id'],
        "title" => $B['title'],
        "url"   => $B['url'],
        "attribution" => $B['attribution'],
        "maxZoom" => $B['maxZoom'] ?? 22
      ];
    }, $basemaps)
  ];

  echo json_encode($out, JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(['error'=>'registry_failed','message'=>$e->getMessage()]);
}
