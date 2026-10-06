# editorial-light

Бумажная журнальная вёрстка: спокойный разбор, академический тон. Образцы
жанра: печатный NYT Magazine, The New Yorker, Granta.

```html
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;1,8..60,400&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

```css
:root {
  --bg: #f7f4ec; --bg-2: #efeadc; --bg-3: #e8e2d0;
  --ink: #1a1812; --ink-dim: #5e5750; --muted: #6f685e;
  --accent: #a84a30; --accent-2: #c1573a;
  --ok: #4a7c4a; --warn: #b8862b; --err: #b04141;
  --rule: #d8d1bf;
  --display: 'Playfair Display', Georgia, serif;
  --body: 'Source Serif 4', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --radius: 4px; --rule-w: 1px;
}
```

Типографика: заголовок страницы 48–110 px Playfair Display 900, заголовок блока
34–54 px Playfair Display 700, подпись 18–19 px Source Serif 4 / 1.65, лид курсивом.

Да: кремовый фон, тёмно-коричневый текст, буквица в первом блоке, щедрые
поля. Нет: белый #fff, чёрный #000, sans в подписях, неоновые акценты.

## Видео

Шкала Full HD без сдвига: титул 120 px Playfair Display 900, заголовок 84 px,
подписи 38 px Source Serif 4, пояснения 30 px, служебный 26 px. Проявление
440 мс с подъёмом 12 px, пауза подписи 480 мс. Линии 4 px цвета `--rule`,
карточки `--bg-2` со скруглением 4 px. Декор: буквица не используется, поля
широкие, иллюстрации линейные в одну толщину.

Переменные для `:root` сцены, поверх блока токенов:

```css
:root {
  --t-title: 120px; --t-h: 84px; --t-copy: 38px; --t-note: 30px; --t-meta: 26px; --display-weight: 700;
  --fade: 440ms; --fade-rise: 12px; --caption-pause: 480ms; --stroke: 4px;
}
```

Акцент текстом на фоне: `--accent` даёт 5.2:1 на `--bg`, им можно писать слова заголовка и метки; `--accent-2` для плоскостей, обводок и состояний, не для текста на фоне.

Все три гарнитуры содержат кириллицу и латиницу; гарнитура без письма языка объяснения молча подменяется браузером, и проверка шрифтов это ловит.
