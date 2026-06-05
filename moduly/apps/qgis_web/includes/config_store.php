<?php
class ConfigStore {
  // --- SETTINGS ---
  public function getSettings(): array { return []; }
  public function saveSettings(array $s): void {}

  // --- LAYERS ---
  public function listLayers(): array { return []; }
  public function getLayer(string $id): ?array { return null; }
  public function saveLayer(array $layer): void {}
  public function deleteLayer(string $id): void {}

  // --- BASEMAPS ---
  public function listBasemaps(): array { return []; }
  public function getBasemap(string $id): ?array { return null; }
  public function saveBasemap(array $rec): void {}
  public function deleteBasemap(string $id): void {}
}

/** JSON souborový store – výchozí */
class FileConfigStore extends ConfigStore {
  private string $file;

  public function __construct(string $file) {
    $this->file = $file;
  }

  private function readAll(): array {
    if (!is_file($this->file)) {
      return ['settings'=>[], 'layers'=>[], 'basemaps'=>[]];
    }
    $json = file_get_contents($this->file);
    $data = json_decode($json, true);
    return is_array($data) ? $data : ['settings'=>[], 'layers'=>[], 'basemaps'=>[]];
  }

  private function writeAll(array $data): void {
    @mkdir(dirname($this->file), 0775, true);
    file_put_contents(
      $this->file,
      json_encode($data, JSON_PRETTY_PRINT|JSON_UNESCAPED_UNICODE)
    );
  }

  // --- SETTINGS ---
  public function getSettings(): array {
    return $this->readAll()['settings'] ?? [];
  }
  public function saveSettings(array $s): void {
    $all = $this->readAll();
    $all['settings'] = $s;
    $this->writeAll($all);
  }

  // --- LAYERS ---
  public function listLayers(): array {
    return $this->readAll()['layers'] ?? [];
  }
  public function getLayer(string $id): ?array {
    foreach ($this->listLayers() as $L) {
      if (($L['id'] ?? '') === $id) return $L;
    }
    return null;
  }
  public function saveLayer(array $layer): void {
    $all = $this->readAll();
    $layers = $all['layers'] ?? [];
    $found = false;
    foreach ($layers as &$L) {
      if (($L['id'] ?? '') === ($layer['id'] ?? '')) {
        $L = $layer; $found = true; break;
      }
    }
    if (!$found) $layers[] = $layer;
    $all['layers'] = $layers;
    $this->writeAll($all);
  }
  public function deleteLayer(string $id): void {
    $all = $this->readAll();
    $all['layers'] = array_values(array_filter(
      $all['layers'] ?? [],
      fn($L) => ($L['id'] ?? '') !== $id
    ));
    $this->writeAll($all);
  }

  // --- BASEMAPS ---
  public function listBasemaps(): array {
    return $this->readAll()['basemaps'] ?? [];
  }
  public function getBasemap(string $id): ?array {
    foreach ($this->listBasemaps() as $B) {
      if (($B['id'] ?? '') === $id) return $B;
    }
    return null;
  }
  public function saveBasemap(array $rec): void {
    $all = $this->readAll();
    $basemaps = $all['basemaps'] ?? [];
    $found = false;
    foreach ($basemaps as &$B) {
      if (($B['id'] ?? '') === ($rec['id'] ?? '')) {
        $B = $rec; $found = true; break;
      }
    }
    if (!$found) $basemaps[] = $rec;
    $all['basemaps'] = $basemaps;
    $this->writeAll($all);
  }
  public function deleteBasemap(string $id): void {
    $all = $this->readAll();
    $all['basemaps'] = array_values(array_filter(
      $all['basemaps'] ?? [],
      fn($B) => ($B['id'] ?? '') !== $id
    ));
    $this->writeAll($all);
  }
}

/** funkce na vrácení správného store */
function config_store(): ConfigStore {
  return new FileConfigStore(__DIR__ . '/../config/app_config.json');
}
?>