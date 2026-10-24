// TUI's Icon still looks string names up in one registry object of 250-odd icons, which
// a bundler can't trim. We pass icon components everywhere (import { Star } from
// '@tangible/ui/icons/system/index.js'), so both builds alias the registry to this
// empty one. A name passed anyway renders an empty span marked data-tui-icon-missing.
export const iconRegistry = {};
