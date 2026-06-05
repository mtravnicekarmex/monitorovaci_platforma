<?php
require_once __DIR__ . '/../../../includes/admin_check.php';
require_once __DIR__ . '/../../../includes/config_store.php';

header('Content-Type: application/json; charset=utf-8');

$payload = json_decode(file_get_contents('php://input'), true) ?: [];

// základní validace
if (empty($payload['id']) || empty($payload['title']) || empty($payload['geomType'])) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid']);
    exit;
}

// === NORMALIZACE PODLE ZDROJE ===
// převod prázdných řetězců na null
$source = $payload['source'] ?? 'static';
$staticData = trim($payload['staticData'] ?? '') ?: null;
$sql = trim($payload['sql'] ?? '') ?: null;

// Výstupní struktura vrstvy
$rec = [
    'id' => $payload['id'],
    'title' => $payload['title'],
    'geomType' => $payload['geomType'],
    'source' => $source,
    'color' => $payload['color'] ?? '#000000',
'priority' => $payload['priority'] ?? 0,
    'specificFilters' => $payload['specificFilters'] ?? []
];

if ($source === 'static') {
    // ukládáme pouze staticData
    $rec['staticData'] = $staticData;
} else if ($source === 'sql') {
    // ukládáme pouze sql dotaz
    $rec['sql'] = $sql;
}

// uložení do app_config.json
$store = config_store();
$store->saveLayer($rec);

echo json_encode(['ok' => true]);
?>
