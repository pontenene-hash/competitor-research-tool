# SEO競合リサーチツール

Google検索上位10件を取得し、順位・タイトル・URL・H2/H3・推定文字数を一覧化するStreamlitアプリです。

## 起動方法

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

ブラウザで `http://localhost:8501` を開きます。デモモードはAPIキーなしで動作します。

## iPhoneで使う方法（おすすめ）

このアプリをStreamlit Community Cloudへ公開すると、iPhoneのSafariからURLを開くだけで使えます。

1. GitHubで無料アカウントを作成します。
2. このフォルダのファイルを、新しいGitHubリポジトリへアップロードします。
3. `share.streamlit.io` にGitHubでログインします。
4. **Create app** を押し、アップロードしたリポジトリを選びます。
5. Main file pathに `app.py` を指定して **Deploy** を押します。
6. 表示されたURLをiPhoneのSafariで開きます。

実データを取得する場合は、Streamlitの **Settings > Secrets** にAPIキーを登録してください。書式は `.streamlit/secrets.toml.example` を参照してください。APIキーをGitHubへ直接アップロードしないでください。

### iPhoneのホーム画面に追加

Safari下部の共有ボタン → **ホーム画面に追加** → **追加** の順にタップすると、アプリのようにワンタップで起動できます。

### スマホ表示

- 検索結果は横長テーブルではなく、順位ごとの縦長カードで表示されます。
- 1位の詳細は最初から開き、2位以下はタップして確認できます。
- 左上の `＞` から検索APIの設定を開けます。

## 実際のGoogle検索結果を取得する

以下のどちらかを利用できます。

1. **Serper API**: SerperでAPIキーを発行し、画面のサイドバーに入力します。
2. **Google Programmable Search**: Google CloudのCustom Search JSON APIを有効化し、APIキーと検索エンジンID（CX）を入力します。

毎回の入力を省く場合は `.env.example` を `.env` にコピーしてキーを設定してください。`.env` は公開リポジトリにコミットしないでください。

## 注意事項

- 対象サイトの利用規約やrobots.txtに従って利用してください。
- JavaScript描画、ログイン必須、bot対策のあるページは解析できない場合があります。
- 推定文字数は、HTML内の本文候補から空白・メニュー等を除いて数えた概算値です。
- Google検索画面そのものをスクレイピングせず、検索APIを使用しています。
