/**
 * 失敗時以指數退避重試，最多 `times` 次。
 */
export async function retry<T>(
  fn: () => Promise<T>,
  times = 3,
  baseDelay = 200,
): Promise<T> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < times; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      const wait = baseDelay * 2 ** attempt; // 200, 400, 800...
      await new Promise((r) => setTimeout(r, wait));
    }
  }
  throw new Error(`重試 ${times} 次仍失敗：${String(lastError)}`);
}

class Cache<K, V> {
  private store = new Map<K, { value: V; expires: number }>();

  get(key: K): V | undefined {
    const hit = this.store.get(key);
    if (!hit || hit.expires < Date.now()) return undefined;
    return hit.value;
  }
}
