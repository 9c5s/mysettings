# 言語別テストパターン リファレンス

テストファイルの検出、フレームワーク、アサーションスタイルを言語別にまとめたリファレンスである。

---

## セクション1: 汎用テストファイル検出ガイド

どの言語にも共通する検出戦略を示す。未知の言語でもこの手順で検出可能である。

### 1-1. プロジェクト設定ファイルからの言語推定

| 設定ファイル | 言語/エコシステム |
|---|---|
| `package.json` | JavaScript / TypeScript |
| `tsconfig.json` | TypeScript |
| `go.mod` | Go |
| `Cargo.toml` | Rust |
| `pyproject.toml`, `setup.py`, `setup.cfg` | Python |
| `pom.xml`, `build.gradle`, `build.gradle.kts` | Java / Kotlin |
| `*.csproj`, `*.sln` | C# / .NET |
| `Gemfile` | Ruby |
| `mix.exs` | Elixir |
| `deno.json`, `deno.jsonc` | Deno (TypeScript) |
| `composer.json` | PHP |
| `Package.swift` | Swift |

### 1-2. テストファイルの一般的な命名規則

以下のパターンはほぼ全ての言語で共通する:

- ファイル名に `test` または `spec` を含む
- 以下のディレクトリ配下に配置される:
  - `tests/`, `test/`, `__tests__/`, `spec/`, `specs/`
  - `src/test/` (Java/Kotlin)
  - `*_test/` (Go - パッケージ内)

### 1-3. テストフレームワーク設定ファイルの検出

| 設定ファイル | フレームワーク |
|---|---|
| `jest.config.*`, `jest.setup.*` | Jest |
| `vitest.config.*` | Vitest |
| `playwright.config.*` | Playwright |
| `cypress.config.*`, `cypress/` | Cypress |
| `pytest.ini`, `conftest.py`, `pyproject.toml[tool.pytest]` | pytest |
| `.rspec` | RSpec |
| `phpunit.xml` | PHPUnit |
| `karma.conf.*` | Karma |

### 1-4. 未知の言語のフォールバック戦略

1. 上記の設定ファイルで言語を推定する
2. `test/`, `tests/`, `spec/`, `__tests__/` ディレクトリを探索する
3. ファイル名に `test`, `spec` を含むファイルを検出する
4. 検出したファイルの内容からテスト構造（アサーション関数、テストブロック等）を推測する
5. t-wadaの9原則は言語非依存であるため、構造を把握できればチェック可能である

---

## セクション2: 主要言語の具体パターン

### Python

**テストファイルパターン**:
- `test_*.py`, `*_test.py`
- `tests/` ディレクトリ配下
- `conftest.py` (フィクスチャ定義)

**フレームワーク**: pytest (推奨), unittest

**Globパターン**:
```
tests/**/*.py
**/test_*.py
**/*_test.py
**/*_spec.py
```

**アサーションスタイル**:
```python
# 基本アサーション
assert result == expected
assert item in collection

# 例外検証
with pytest.raises(ValueError, match="must be positive"):
    func(-1)

# パラメータ化テスト
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
])
def test_double(input, expected):
    assert double(input) == expected
```

**特記事項**:
- `conftest.py` でフィクスチャを共有する
- `@pytest.mark.parametrize` でテストケースを分離する
- `pytest.raises` で例外メッセージまで検証する

---

### TypeScript / JavaScript

**テストファイルパターン**:
- `*.test.ts`, `*.spec.ts`, `*.test.tsx`, `*.spec.tsx`
- `*.test.js`, `*.spec.js`, `*.test.jsx`, `*.spec.jsx`
- `__tests__/` ディレクトリ配下

**フレームワーク**: Vitest (推奨), Jest

**Globパターン**:
```
**/*.test.ts
**/*.spec.ts
**/*.test.tsx
**/*.spec.tsx
**/*.test.js
**/*.spec.js
**/__tests__/**/*.[jt]s?(x)
```

**アサーションスタイル**:
```typescript
// 基本アサーション
expect(result).toBe(expected);
expect(result).toEqual({ name: "Alice" });

// 例外検証
expect(() => func(-1)).toThrow("must be positive");

// 非同期
await expect(asyncFunc()).resolves.toBe(expected);
await expect(asyncFunc()).rejects.toThrow("error");

// パラメータ化テスト
describe.each([
  [1, 2],
  [2, 4],
])("double(%i)", (input, expected) => {
  it(`returns ${expected}`, () => {
    expect(double(input)).toBe(expected);
  });
});
```

**特記事項**:
- `describe.each` / `it.each` でパラメータ化テストを行う
- `beforeEach` / `afterEach` でセットアップ/クリーンアップを行う
- snapshotテストの過剰使用は避ける（変更への脆さの原因になる）

---

### React

**テストファイルパターン**: TypeScript/JavaScriptと同じ（`.tsx`, `.jsx` ファイル）

**フレームワーク**: React Testing Library + Vitest/Jest

**クエリ優先順位** (Testing Library公式ガイドライン):

| 優先度 | クエリ | 用途 |
|---|---|---|
| 1 (最優先) | `getByRole` | アクセシビリティロールで取得 |
| 2 | `getByLabelText` | フォーム要素 |
| 3 | `getByPlaceholderText` | プレースホルダーで取得 |
| 4 | `getByText` | テキストコンテンツで取得 |
| 5 | `getByDisplayValue` | フォームの現在値 |
| 6 | `getByAltText` | 画像のalt属性 |
| 7 | `getByTitle` | title属性 |
| 8 (最終手段) | `getByTestId` | data-testid属性 |

**ユーザーイベント**:
```typescript
// userEvent > fireEvent (ユーザーの実際の操作に近い)
import userEvent from "@testing-library/user-event";

const user = userEvent.setup();
await user.click(screen.getByRole("button", { name: "送信" }));
await user.type(screen.getByRole("textbox"), "Hello");
```

**アンチパターン**:
- `getByTestId` の過剰使用 - アクセシビリティクエリを優先する
- 実装詳細への依存 - コンポーネントの内部state/propsを直接テストしない
- `container.querySelector` の使用 - Testing Libraryのクエリを使う
- `act()` の手動呼び出し - Testing Libraryが内部で処理する

---

### Go

**テストファイルパターン**:
- `*_test.go` (同一パッケージ内に配置)

**フレームワーク**: `testing` (標準), testify

**Globパターン**:
```
**/*_test.go
```

**アサーションスタイル**:

```go
// 標準ライブラリ
func TestAdd(t *testing.T) {
    got := Add(1, 2)
    want := 3
    if got != want {
        t.Errorf("Add(1, 2) = %d, want %d", got, want)
    }
}

// testify
func TestAdd(t *testing.T) {
    assert.Equal(t, 3, Add(1, 2))
    require.NoError(t, err)
}
```

**テーブルドリブンテスト** (Go標準パターン):
```go
func TestAdd(t *testing.T) {
    tests := []struct {
        name string
        a, b int
        want int
    }{
        {"positive", 1, 2, 3},
        {"zero", 0, 0, 0},
        {"negative", -1, -2, -3},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := Add(tt.a, tt.b)
            if got != tt.want {
                t.Errorf("Add(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
            }
        })
    }
}
```

**`t.Parallel()` と変数キャプチャ**:
```go
// 正しい: ループ変数をキャプチャする
for _, tt := range tests {
    tt := tt // Go 1.21以前では必須
    t.Run(tt.name, func(t *testing.T) {
        t.Parallel()
        got := Add(tt.a, tt.b)
        assert.Equal(t, tt.want, got)
    })
}
```

**特記事項**:
- テーブルドリブンテストがGoのイディオムである
- `t.Helper()` でヘルパー関数のスタックトレースを改善する
- `t.Parallel()` 使用時はループ変数のキャプチャに注意する（Go 1.22以降は不要）
- ブラックボックステストには `_test` パッケージサフィックスを使用する

---

## セクション3: その他の言語（簡易リファレンス）

将来の拡張ポイントとして、追加言語のパターンを簡潔に記載する。

### Rust
- テストファイル: `#[cfg(test)]` モジュール（同一ファイル内）, `tests/` ディレクトリ（統合テスト）
- アサーション: `assert!()`, `assert_eq!()`, `assert_ne!()`
- Globパターン: `tests/**/*.rs`, `src/**/*.rs`（`#[cfg(test)]`を含むファイル）

### Java / Kotlin
- テストファイル: `*Test.java`, `*Spec.kt`, `*Tests.java`
- ディレクトリ: `src/test/java/`, `src/test/kotlin/`
- フレームワーク: JUnit 5, Kotest
- Globパターン: `src/test/**/*.java`, `src/test/**/*.kt`

### C# / .NET
- テストファイル: `*Tests.cs`, `*Test.cs`
- プロジェクト: `*.Test.csproj`, `*.Tests.csproj`
- フレームワーク: xUnit, NUnit, MSTest
- Globパターン: `**/*Tests.cs`, `**/*Test.cs`

### Ruby
- テストファイル: `*_spec.rb` (RSpec), `*_test.rb` (Minitest)
- ディレクトリ: `spec/` (RSpec), `test/` (Minitest)
- フレームワーク: RSpec, Minitest
- Globパターン: `spec/**/*_spec.rb`, `test/**/*_test.rb`

### PHP
- テストファイル: `*Test.php`
- ディレクトリ: `tests/`
- フレームワーク: PHPUnit, Pest
- Globパターン: `tests/**/*Test.php`

### Elixir
- テストファイル: `*_test.exs`
- ディレクトリ: `test/`
- フレームワーク: ExUnit
- Globパターン: `test/**/*_test.exs`
