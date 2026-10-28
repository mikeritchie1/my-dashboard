const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../docs/app.js"), "utf8");
function extract(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Missing function ${name}`);
  const end = source.indexOf("\nfunction ", start + 1);
  return source.slice(start, end < 0 ? undefined : end);
}
const section = { open: false };
let closed = false;
let scrolled = false;
let centered = null;
let rendered = 0;
let detail = null;
const context = vm.createContext({
  state: {
    specialsPayload: {}, mapSources: { events: false },
    availableMapTypes: [], availableMapCategories: [], availableEventCategories: [],
    selectedMapTypes: new Set(), selectedMapCategories: new Set(), selectedEventCategories: new Set(),
    quicketEvents: [], bandsintownEvents: [],
  },
  focusedMapEvent: null, selectedMapItemKey: "",
  TIMEZONE: "Africa/Johannesburg", WEEK_DAYS: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
  coordinatesFor: event => Number.isFinite(event.lat) && Number.isFinite(event.lng)
    ? { lat: event.lat, lng: event.lng } : null,
  mapRangeWindow: () => ({ start: new Date("2026-10-28"), end: new Date("2026-11-04") }),
  displayDateTime: value => value || "", categorizeEvent: () => [],
  placeMatchForEvent: () => false,
  renderMap: () => { rendered++; }, renderMapDetail: item => { detail = item; },
  elements: {
    specialsMap: { closest: () => section, scrollIntoView: () => { scrolled = true; } },
    watchlistDetailClose: { click: () => { closed = true; } },
  },
  specialsMap: { invalidateSize() {}, setView: coords => { centered = coords; } },
});
vm.runInContext(["mapItemFromEvent", "mapItemKey", "buildMapItems", "focusEventOnMap"]
  .map(extract).join("\n"), context);

const event = { title: "Future concert", start: "2026-12-20T19:00:00+02:00", lat: -33.9, lng: 18.4, url: "https://example.com/event" };
assert.equal(context.mapItemFromEvent(event), null, "Ordinary events still respect the selected dates");
assert.equal(context.buildMapItems().length, 0);
context.focusEventOnMap(event);
assert.equal(context.focusedMapEvent, event);
assert.equal(context.buildMapItems()[0].event, event, "Selected event bypasses date and source filters");
assert.equal(section.open, true);
assert.equal(closed, true);
assert.equal(scrolled, true);
assert.deepEqual(Array.from(centered), [-33.9, 18.4]);
assert.equal(detail.event, event);
assert.equal(rendered, 1);

context.state.mapSources.events = true;
context.state.quicketEvents = [event];
context.mapRangeWindow = () => ({ start: new Date("2026-12-01"), end: new Date("2026-12-31") });
assert.equal(context.buildMapItems().length, 1, "Selected event is not duplicated when it matches the filters");
context.focusedMapEvent = null;
context.state.mapSources.events = false;
assert.equal(context.buildMapItems().length, 0, "Clearing the override restores ordinary filters");
context.focusEventOnMap({ title: "No coordinates" });
assert.equal(context.focusedMapEvent, null);
assert.equal(rendered, 1, "Unmapped events cannot trigger a map jump");

// Back to map view must remove the temporary event and redraw the filtered markers.
context.focusedMapEvent = event;
vm.runInContext(extract("renderMapDetail"), context);
context.renderMapDetail(null);
assert.equal(context.focusedMapEvent, null);
assert.equal(context.selectedMapItemKey, "");
assert.equal(rendered, 2);
console.log("Event map checks passed");
