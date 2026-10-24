// The specimen's icon registry: only the icons it can show. TUI's Icon looks names up
// in one registry object, so a bundler can't drop the 250-odd unused icons (~100 kB);
// vite.specimen.config.ts swaps this module in for it. An icon missing here renders
// nothing and warns in the console, so add any new one the specimen starts using.
import { Check, ChevronRight, Close, ExternalLink, MoonOutline, SunOutline } from '@tangible/ui/icons/system/index.js';

export const iconRegistry = {
  'system/check': Check,                // Switch
  'system/chevron-right': ChevronRight, // Button and Card internals
  'system/close': Close,                // Notice dismiss
  'system/external-link': ExternalLink, // Button opening a new tab
  'system/moon-outline': MoonOutline,   // theme button
  'system/sun-outline': SunOutline,     // theme button
};
