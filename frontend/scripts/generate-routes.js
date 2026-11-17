import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const routes = [
  'login',
  'employees',
  'departments',
  'attendance',
  'shifts',
  'leave',
  'anomalies',
  'ai',
  'policies',
  'analytics',
  'notifications',
  'audit-logs',
  'diagnostics',
  'settings',
  'help',
  '403',
  '404',
  '500'
];

const distDir = path.resolve(__dirname, '..', 'dist');

if (!fs.existsSync(distDir)) {
  console.error('Dist directory does not exist. Run vite build first.');
  process.exit(1);
}

const indexPath = path.join(distDir, 'index.html');
const indexHtml = fs.readFileSync(indexPath, 'utf-8');

// 1. Generate 404.html fallback
fs.writeFileSync(path.join(distDir, '404.html'), indexHtml, 'utf-8');

// 2. Generate physical directory index.html and .html files for every route
for (const r of routes) {
  const dir = path.join(distDir, r);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(path.join(dir, 'index.html'), indexHtml, 'utf-8');
  fs.writeFileSync(path.join(distDir, `${r}.html`), indexHtml, 'utf-8');
}

console.log(`[SPA Route Generator] Successfully generated physical HTML entrypoints for ${routes.length} routes + 404.html.`);
