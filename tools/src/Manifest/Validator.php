<?php

declare(strict_types=1);

/**
 * Copyright 2022-2026 FOSSBilling
 * SPDX-License-Identifier: Apache-2.0.
 *
 * @copyright FOSSBilling (https://www.fossbilling.org)
 * @license http://www.apache.org/licenses/LICENSE-2.0 Apache-2.0
 */

namespace FOSSBilling\Tools\Manifest;

use Composer\Semver\VersionParser;
use Composer\Spdx\SpdxLicenses;
use JsonSchema\Validator as SchemaValidator;
use RuntimeException;
use stdClass;
use Symfony\Component\Finder\Finder;
use UnexpectedValueException;

/**
 * Validates package manifest.json files against the manifest JSON schema plus
 * project-specific checks that the schema cannot express.
 *
 * Mirrors the Validator in FOSSBilling/FOSSBilling tools; the package discovery
 * and icon rules are specific to this repository (published extensions carry a
 * package-relative `icon_url`, and only `tools` is not a package).
 */
final readonly class Validator
{
    public function __construct(
        private readonly string $modulesDir,
        private readonly string $schemaPath,
    ) {}

    /**
     * Validate every package directory beneath $modulesDir.
     *
     * @return array{packages: int, failures: list<string>, lines: list<string>}
     *
     * @throws RuntimeException when no package directories are found
     */
    public function validate(): array
    {
        $finder = new Finder();
        $finder->directories()->in($this->modulesDir)->depth('== 0')->sortByName();
        $packages = array_map(static fn ($file) => $file->getPathname(), iterator_to_array($finder, false));
        // Only module packages carry a manifest; dotdirs and tooling are not packages.
        $packages = array_values(array_filter(
            $packages,
            static fn (string $dir): bool => basename($dir)[0] !== '.' && basename($dir) !== 'tools',
        ));
        if ($packages === []) {
            throw new RuntimeException("No module directories found under {$this->modulesDir}");
        }

        $parser = new VersionParser();
        $spdx = new SpdxLicenses();
        $failures = [];
        $lines = [];

        foreach ($packages as $dir) {
            $id = basename($dir);
            $errors = [];
            if (!is_file($dir . '/manifest.json')) {
                $errors[] = 'manifest.json is missing';
                $lines = $this->result($id, $errors, $failures, $lines);

                continue;
            }
            $raw = file_get_contents($dir . '/manifest.json');
            $data = json_decode((string) $raw);
            if (!$data instanceof stdClass) {
                $errors[] = 'manifest.json is not valid JSON';
                $lines = $this->result($id, $errors, $failures, $lines);

                continue;
            }

            $validator = new SchemaValidator();
            $validator->validate($data, (object) ['$ref' => 'file://' . $this->schemaPath]);
            if (!$validator->isValid()) {
                foreach ($validator->getErrors() as $e) {
                    $errors[] = sprintf('[%s] %s', $e['property'] ?: '(root)', $e['message']);
                }
            }

            $m = json_decode((string) $raw, true);
            if (($m['type'] ?? null) !== 'module') {
                $errors[] = 'type must be "module" in this repo';
            }
            if (strtolower($id) !== ($m['id'] ?? null)) {
                $errors[] = sprintf('id "%s" must match directory "%s" (case-insensitive)', $m['id'] ?? '?', $id);
            }
            foreach (['author.url' => $m['author']['url'] ?? null, 'homepage_url' => $m['homepage_url'] ?? null] as $field => $url) {
                if ($url !== null && (!filter_var($url, FILTER_VALIDATE_URL) || !in_array(strtolower((string) parse_url($url, PHP_URL_SCHEME)), ['http', 'https'], true))) {
                    $errors[] = $field . ' must be an http(s) URL';
                }
            }
            if (isset($m['icon_url'])) {
                $icon = $m['icon_url'];
                $resolved = realpath($dir . '/' . $icon) ?: $dir . '/' . $icon;
                $base = realpath($dir);
                if (!is_file($dir . '/' . $icon) || $base === false || !str_starts_with($resolved, $base . DIRECTORY_SEPARATOR)) {
                    $errors[] = 'icon_url target missing or escapes package dir';
                }
            }

            try {
                $parser->normalize($m['version'] ?? '');
                if (str_starts_with((string) ($m['version'] ?? ''), 'v')) {
                    $errors[] = 'version must not have a "v" prefix';
                }
            } catch (UnexpectedValueException) {
                $errors[] = 'version is not valid semver';
            }
            foreach (['fossbilling' => $m['requires']['fossbilling'] ?? null, 'php' => $m['requires']['php'] ?? null] as $field => $c) {
                try {
                    $parser->parseConstraints((string) $c);
                } catch (UnexpectedValueException) {
                    $errors[] = "requires.{$field} is not a valid composer/semver constraint";
                }
            }
            foreach ($m['requires']['modules'] ?? [] as $dep => $c) {
                if ($dep === ($m['id'] ?? null)) {
                    $errors[] = 'requires.modules must not self-reference';
                }

                try {
                    $parser->parseConstraints((string) $c);
                } catch (UnexpectedValueException) {
                    $errors[] = "requires.modules.{$dep} is not a valid constraint";
                }
            }
            if (!$spdx->validate((string) ($m['license'] ?? ''))) {
                $errors[] = 'license is not a valid SPDX expression';
            }

            $lines = $this->result($id, $errors, $failures, $lines);
        }

        return ['packages' => count($packages), 'failures' => $failures, 'lines' => $lines];
    }

    /**
     * @param list<string> $errors
     * @param list<string> $failures
     * @param list<string> $lines
     *
     * @return list<string>
     */
    private function result(string $id, array $errors, array &$failures, array $lines): array
    {
        if ($errors === []) {
            $lines[] = "PASS {$id}";

            return $lines;
        }
        $failures[] = $id;
        $lines[] = "FAIL {$id}";
        foreach ($errors as $error) {
            $lines[] = "  - {$error}";
        }

        return $lines;
    }
}
