# t-wada式TDD原則リファレンス

t-wada（和田卓人）氏が提唱するテスト駆動開発の原則と実践をまとめたリファレンスである。

## Kent BeckのTDD 5ステップ

TDDの基本サイクルはKent Beckが定義した以下の5ステップで構成される:

1. **テストを1つ書く** - まず失敗するテストを書く
2. **テストを実行し、失敗を確認する（Red）** - テストが期待通りに失敗することを確認する
3. **テストをパスする最小限のコードを書く（Green）** - 動く最小限の実装を行う
4. **テストを実行し、成功を確認する** - テストが通ることを確認する
5. **リファクタリングする（Refactor）** - 重複を除去し設計を改善する

このRed-Green-Refactorサイクルを繰り返すことで、テストに守られた堅牢なコードを構築する。

> 出典: Kent Beck, "Test-Driven Development: By Example" (2002)

## 原則1: AAAパターン（Arrange-Act-Assert）

### 定義

テストを3つの明確なフェーズに分離するパターンである。

- **Arrange（準備）**: テストに必要なオブジェクト、データ、前提条件を準備する
- **Act（実行）**: テスト対象の操作を1つだけ実行する
- **Assert（検証）**: 操作の結果が期待通りであることを検証する

### 根拠

フェーズを明確に分離することで、テストの意図が読み取りやすくなる。特にActが1つであることが重要で、複数の操作を1つのテストに詰め込むとテストが何を検証しているか不明確になる。

### 良い例

```python
def test_add_item_increases_count(self) -> None:
    """カートにアイテムを追加するとカウントが増えること"""
    # Arrange
    cart = ShoppingCart()
    item = Item("apple", 100)

    # Act
    cart.add(item)

    # Assert
    assert cart.count == 1
```

### 悪い例

```python
def test_cart_operations(self) -> None:
    cart = ShoppingCart()
    cart.add(Item("apple", 100))
    assert cart.count == 1       # Actの直後にAssert
    cart.add(Item("banana", 200))  # 2つ目のAct
    assert cart.count == 2
    cart.remove("apple")           # 3つ目のAct
    assert cart.total == 200
```

> 出典: Bill Wake, "3A - Arrange, Act, Assert" (2001)
> https://xp123.com/articles/3a-arrange-act-assert/

## 原則2: One Assertion Per Test

### 定義

1つのテストには「意味のあるひとまとまり」のアサーションのみを含めるべきである。

### 根拠

テストが失敗した時、何が壊れたかを即座に特定できるようにするためである。無関係な複数のアサーションを1テストに詰め込むと、最初のアサーション失敗で後続が実行されず、問題の全体像が見えなくなる。

ただし、1つの振る舞いを検証するために複数のアサーションが必要な場合は許容される（例: オブジェクトの複数プロパティの検証）。

### 良い例

```python
def test_user_creation_sets_name(self) -> None:
    user = User("Alice", "alice@example.com")
    assert user.name == "Alice"

def test_user_creation_sets_email(self) -> None:
    user = User("Alice", "alice@example.com")
    assert user.email == "alice@example.com"
```

```python
# 関連プロパティのグループ検証も許容される
def test_parse_returns_correct_address(self) -> None:
    address = parse_address("東京都渋谷区1-2-3")
    assert address.prefecture == "東京都"
    assert address.city == "渋谷区"
    assert address.street == "1-2-3"
```

### 悪い例

```python
def test_user(self) -> None:
    user = User("Alice", "alice@example.com")
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
    assert user.is_active is True
    assert user.created_at is not None
    # さらにログインの検証まで...
    user.login("password")
    assert user.is_logged_in is True
```

> 出典: Roy Osherove, "The Art of Unit Testing" (2009)

## 原則3: アサーション情報量（Power Assert）

### 定義

テスト失敗時に、期待値と実際値が明確に分かるアサーションを書くべきである。t-wada氏はpower-assertの開発者であり、失敗時の情報量を重視する。

### 根拠

テストが失敗した時、デバッガを使わなくてもアサーションメッセージだけで原因を特定できることが理想である。情報量の少ないアサーションは、失敗時の調査コストを増大させる。

### 良い例

```python
# 期待値と実際値が明確
assert result == 42
assert user.name == "Alice"
assert len(items) == 3

# pytest.raisesでメッセージも検証
with pytest.raises(ValueError, match="must be positive"):
    create_item(-1)
```

### 悪い例

```python
# 情報量が少ない - 失敗時に何が問題か分からない
assert result
assert not error
assert len(items)  # 0でないことしか分からない
assert isinstance(result, dict)  # 中身が分からない

# 例外の型だけで内容を検証しない
with pytest.raises(ValueError):
    create_item(-1)
```

> 出典: t-wada, "power-assert - Power Assert in JavaScript"
> https://github.com/power-assert-js/power-assert

## 原則4: 自作自演の回避

### 定義

テストコード内で期待値を計算するロジックが、プロダクションコードと同じロジックを再実装してはならない。

### 根拠

テストとプロダクションコードが同じバグを持つ場合、テストは通るがプログラムは壊れているという最悪の状態になる。期待値はリテラル（ハードコーディング値）で記述するか、別の方法で算出するべきである。

### 良い例

```python
def test_tax_calculation(self) -> None:
    # 期待値をリテラルで記述
    assert calculate_tax(1000, rate=0.1) == 100

def test_discount_price(self) -> None:
    # 三角測量: 複数の具体例で検証
    assert apply_discount(1000, 10) == 900
    assert apply_discount(500, 20) == 400
```

### 悪い例

```python
def test_tax_calculation(self) -> None:
    price = 1000
    rate = 0.1
    # プロダクションコードと同じ計算をテストで再実装している
    expected = price * rate
    assert calculate_tax(price, rate=rate) == expected
```

> 出典: t-wada, "プログラマが知るべき97のこと - テストは正確に、具体的に"
> https://xp123.com/articles/3a-arrange-act-assert/

## 原則5: テストのドキュメント性

### 定義

テストはそれ自体がドキュメントとして機能するべきである。テスト名、構造、docstringから、テスト対象の仕様と意図が読み取れなければならない。

### 根拠

テストは「実行可能な仕様書」である。テストが失敗した時、テスト名だけでどの仕様が壊れたかを判断できることが理想である。

### 良い例

```python
class TestShoppingCart:
    """ショッピングカートの振る舞い"""

    def test_empty_cart_has_zero_total(self) -> None:
        """空のカートの合計金額が0であること"""
        cart = ShoppingCart()
        assert cart.total == 0

    def test_add_item_increases_total_by_item_price(self) -> None:
        """アイテム追加で合計金額がアイテムの価格分増えること"""
        cart = ShoppingCart()
        cart.add(Item("apple", 100))
        assert cart.total == 100
```

### 悪い例

```python
class TestCart:
    def test_1(self) -> None:
        c = ShoppingCart()
        assert c.total == 0

    def test_2(self) -> None:
        c = ShoppingCart()
        c.add(Item("a", 100))
        assert c.total == 100
```

> 出典: Gerard Meszaros, "xUnit Test Patterns" (2007)

## 原則6: モックの最小化

### 定義

モック（テストダブル）は外部依存の境界にのみ使用し、内部実装のモックは避けるべきである。

### 根拠

過剰なモックはテストを脆くする。実装のリファクタリングでテストが壊れるようでは、テストがリファクタリングの安全網として機能しない。モックはI/O、ネットワーク、時刻、乱数などの非決定的な外部依存に限定するべきである。

### 良い例

```python
def test_send_notification(self) -> None:
    """通知が外部APIに送信されること"""
    # 外部依存（HTTPクライアント）のみをモック
    with patch("app.notifications.http_client.post") as mock_post:
        mock_post.return_value = Response(200)
        send_notification("Hello")
        mock_post.assert_called_once()
```

### 悪い例

```python
def test_process_order(self) -> None:
    # 内部の全メソッドをモックしている
    with patch.object(order, "_validate") as mock_validate, \
         patch.object(order, "_calculate_total") as mock_calc, \
         patch.object(order, "_apply_discount") as mock_discount:
        mock_validate.return_value = True
        mock_calc.return_value = 1000
        mock_discount.return_value = 900
        order.process()
        # 実装の詳細に完全に依存している
```

> 出典: Martin Fowler, "Mocks Aren't Stubs" (2007)
> https://martinfowler.com/articles/mocksArentStubs.html

## 原則7: 偽陰性の回避

### 定義

テストにはアサーションが必ず含まれていなければならない。アサーションのないテストは常にパスするため、テストとして機能しない。

### 根拠

アサーションゼロのテストは「偽陰性（false negative）」を生む。コードが壊れていてもテストがパスするため、テストスイートへの信頼を損なう。

### 良い例

```python
def test_parse_raises_on_invalid_input(self) -> None:
    """不正な入力で例外が発生すること"""
    with pytest.raises(ValueError, match="invalid format"):
        parse("invalid")
```

### 悪い例

```python
def test_process(self) -> None:
    """処理が正常に完了すること"""
    result = process(data)
    # アサーションがない - 常にパスする

def test_no_error(self) -> None:
    """エラーが発生しないこと"""
    try:
        risky_operation()
    except Exception:
        pass  # 例外を握りつぶしている
```

> 出典: t-wada, "テスト駆動開発" 講演資料
> https://speakerdeck.com/twada

## 原則8: テストサイズ（テストピラミッド）

### 定義

テストスイートはSmall（単体）テストを土台としたピラミッド型で構成するべきである。

- **Small**: 外部依存なし。メモリ内で完結。高速（ミリ秒単位）
- **Medium**: ローカルリソース（DB、ファイルシステム等）に依存。やや低速（秒単位）
- **Large**: ネットワークや外部サービスに依存。低速（秒〜分単位）

### 根拠

Smallテストが多いほど、フィードバックループが短くなり、TDDのRed-Green-Refactorサイクルを高速に回せる。Largeテストは実行が遅く不安定（flaky）になりやすいため、最小限に留めるべきである。

### 理想的な比率

```
        /\
       /  \   Large  (~5%)
      /----\
     /      \  Medium (~15%)
    /--------\
   /          \ Small  (~80%)
  /____________\
```

> 出典: Mike Cohn, "Succeeding with Agile" (2009)
> Google Testing Blog, "Test Sizes"
> https://testing.googleblog.com/2010/12/test-sizes.html

## 原則9: テストケースの十分性

### 定義

テストスイートはプロダクションコードのテスト可能な関数・クラスを十分にカバーしているべきである。テスト品質が高くても、テスト対象外の関数が存在すればプロダクションコードの信頼性は保証されない。

### 根拠

テストの品質（原則1〜8）が高くても、テスト対象のカバレッジが不十分であれば、テストスイートとしての価値は限定的である。特に純粋関数やユーティリティ関数のようにテストしやすいコードがテストされていない場合、それは見落としである可能性が高い。TDDの本質は「テストに守られたコード」であり、守られていないコードが存在すること自体がリスクである。

### テスト可能性による優先度

テスト対象の関数は以下の分類で優先度付けする:

1. **純粋関数（最優先）**: 入力に対して決定的な出力を返す関数。副作用がなく、テストが容易
2. **ユーティリティ関数（高優先）**: 文字列処理、データ変換等の汎用的な関数
3. **ビジネスロジック（高優先）**: ドメインルールを実装する関数・メソッド
4. **I/O依存（中優先）**: ファイル操作、ネットワーク通信等。モックを用いてテスト可能
5. **エントリポイント/グルーコード（低優先）**: main関数、CLI引数パーサーの呼び出し等。統合テストで間接的にカバーされることが多い

### コードパス分析

テスト済みの関数についても、主要なコードパスがカバーされているかを確認する:

- 正常系パス
- 異常系パス（エラーケース、エッジケース）
- 分岐条件の各パス（if/else、match/case等）

### 良い例

```python
# プロダクションコード
def calculate_total(items: list[Item]) -> int: ...
def apply_discount(total: int, rate: float) -> int: ...
def format_receipt(items: list[Item], total: int) -> str: ...

# テストコード - 全ての関数がテストされている
class TestCalculateTotal:
    def test_empty_list_returns_zero(self) -> None: ...
    def test_single_item(self) -> None: ...
    def test_multiple_items(self) -> None: ...

class TestApplyDiscount:
    def test_zero_discount(self) -> None: ...
    def test_normal_discount(self) -> None: ...
    def test_full_discount(self) -> None: ...

class TestFormatReceipt:
    def test_empty_receipt(self) -> None: ...
    def test_receipt_with_items(self) -> None: ...
```

### 悪い例

```python
# プロダクションコード - 3つの関数がある
def calculate_total(items: list[Item]) -> int: ...
def apply_discount(total: int, rate: float) -> int: ...
def format_receipt(items: list[Item], total: int) -> str: ...

# テストコード - calculate_totalしかテストされていない
class TestCalculateTotal:
    def test_empty_list_returns_zero(self) -> None: ...
    def test_single_item(self) -> None: ...
    # apply_discountとformat_receiptのテストが存在しない
```

> 出典: t-wada, "質とスピード" 講演 - テストカバレッジと信頼性の関係
> https://speakerdeck.com/twada/quality-and-speed
> Martin Fowler, "TestCoverage" (2012)
> https://martinfowler.com/bliki/TestCoverage.html

## 追加の参考資料

- t-wada, "プログラマが知るべき97のこと" 寄稿
- t-wada, "テスト駆動開発" 翻訳 (Kent Beck著)
- t-wada, "質とスピード" 講演
  - https://speakerdeck.com/twada/quality-and-speed
- t-wada, "TDD Boot Camp" 資料
  - https://speakerdeck.com/twada
- Kent Beck, "Test-Driven Development: By Example" (2002)
- Gerard Meszaros, "xUnit Test Patterns" (2007)
- Roy Osherove, "The Art of Unit Testing" (2009)
