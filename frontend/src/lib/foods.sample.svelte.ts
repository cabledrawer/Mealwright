// PLACEHOLDER kitchen, so the Ingredients screen and the editor can be laid out before
// the 0.2 API exists. Replaced by data from /api/v1 as soon as it does.

import type { Food, Place, Shop } from './foods';

const places: Place[] = [
  { id: 1, name: 'Fridge' },
  { id: 2, name: 'Freezer' },
  { id: 3, name: 'Cupboard' },
  { id: 4, name: 'Spice rack' }
];

const shops: Shop[] = [
  { id: 1, name: 'Spice Bazaar' },
  { id: 2, name: 'Tesco' },
  { id: 3, name: 'Lidl' }
];

const foods: Food[] = [
  {
    id: 1,
    name: 'Toor dal',
    otherNames: ['thuvaram paruppu', 'arhar dal'],
    base: 'g',
    saleUnits: [
      { name: 'packet', amount: 500, usual: true },
      { name: 'bag', amount: 1000, usual: false, note: 'added when shopping' }
    ],
    cupWeight: '200 g',
    runningLow: '½ packet',
    placeId: 3,
    shopId: 1,
    staple: false,
    standInIds: [5]
  },
  {
    id: 2,
    name: 'Onion',
    otherNames: [],
    base: 'count',
    saleUnits: [],
    cupWeight: '',
    runningLow: '2',
    placeId: 3,
    shopId: 2,
    staple: false,
    standInIds: [7]
  },
  {
    id: 3,
    name: 'Bread',
    otherNames: [],
    base: 'count',
    countName: 'slice',
    saleUnits: [{ name: 'loaf', amount: 20, usual: true }],
    cupWeight: '',
    runningLow: '4 slices',
    placeId: 3,
    shopId: 2,
    staple: false,
    standInIds: []
  },
  {
    id: 4,
    name: 'Turmeric',
    otherNames: ['manjal'],
    base: 'g',
    saleUnits: [{ name: 'packet', amount: 100, usual: true }],
    cupWeight: '',
    runningLow: '',
    placeId: 4,
    shopId: 1,
    staple: true,
    standInIds: []
  },
  {
    id: 5,
    name: 'Moong dal',
    otherNames: ['pasi paruppu'],
    base: 'g',
    saleUnits: [{ name: 'packet', amount: 500, usual: true }],
    cupWeight: '200 g',
    runningLow: '',
    placeId: 3,
    shopId: 1,
    staple: false,
    standInIds: []
  },
  {
    id: 6,
    name: 'Drumsticks (moringa)',
    otherNames: [],
    base: 'count',
    saleUnits: [],
    cupWeight: '',
    runningLow: '',
    placeId: 2,
    shopId: 1,
    staple: false,
    standInIds: [],
    maybeSameAsId: 8
  },
  {
    id: 7,
    name: 'Red onion',
    otherNames: [],
    base: 'count',
    saleUnits: [],
    cupWeight: '',
    runningLow: '',
    placeId: 3,
    shopId: 2,
    staple: false,
    standInIds: []
  },
  {
    id: 8,
    name: 'Drumsticks',
    otherNames: [],
    base: 'count',
    saleUnits: [],
    cupWeight: '',
    runningLow: '',
    placeId: 2,
    shopId: 1,
    staple: false,
    standInIds: [],
    maybeSameAsId: 6
  }
];

export const kitchen = $state({ foods, places, shops });

export function foodById(id: number | null | undefined): Food | undefined {
  return kitchen.foods.find((food) => food.id === id);
}
