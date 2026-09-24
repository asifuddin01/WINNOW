import { removeTestData } from "./support/cleanup";

/** Runs once after the suite: nothing the tests made is kept (see support/cleanup.ts). */
export default function globalTeardown(): void {
  removeTestData();
}
