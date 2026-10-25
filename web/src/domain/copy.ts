// SPDX-License-Identifier: AGPL-3.0-or-later
// The local copy of the collections, kept current with `GET /api/v1/sync`.
import type { Collection, Plant, Sync } from "../api/types";

export interface Copy {
  cursor: string;
  collections: Map<string, Collection>;
  plants: Map<string, Plant>;
}

/** A `full` sync replaces the copy; a `delta` changes it. The old copy is left as it was. */
export function applySync(copy: Copy | null, sync: Sync): Copy {
  const full = sync.kind === "full" || copy === null;
  const collections = new Map(full ? [] : copy.collections);
  const plants = new Map(full ? [] : copy.plants);
  for (const id of sync.removed_collections) collections.delete(id);
  for (const id of sync.removed_plants) plants.delete(id);
  for (const collection of sync.collections) collections.set(collection.id, collection);
  for (const plant of sync.plants) plants.set(plant.id, plant);
  return { cursor: sync.cursor, collections, plants };
}

export const plantsOf = (copy: Copy, collectionId: string): Plant[] =>
  [...copy.plants.values()].filter((plant) => plant.collection_id === collectionId);
