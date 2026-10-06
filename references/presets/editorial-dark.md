# editorial-dark

Тёмная журнальная вёрстка: серьёзный материал, длинное чтение. Образцы жанра:
Stripe Press, Quanta Magazine, The Pudding. Умолчание, если человек не выбрал.

```html
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&family=Spectral:ital,wght@0,400;0,500;0,600;1,400;1,500&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

```css
:root {
  --bg: #0d0f12; --bg-2: #14171c; --bg-3: #1a1e25;
  --ink: #ededeb; --ink-dim: #b8b4ad; --muted: #8c8880;
  --accent: #d97757; --accent-2: #f0916d;
  --ok: #88b88a; --warn: #d4a85b; --err: #c87171;
  --rule: #1f2530;
  --display: 'Playfair Display', Georgia, serif;
  --body: 'Spectral', Georgia, serif;
  --mono: 'JetBrains Mono', monospace;
  --radius: 6px; --rule-w: 1px;
}
```

Типографика: заголовок страницы 56–120 px Playfair Display 700, заголовок блока
36–56 px Playfair Display 700 с одним словом курсивом в цвете акцента, подпись 18 px
Spectral / 1.6, метки 11 px JetBrains Mono.

Да: тёплый off-white текст, один акцент терракота, сноски курсивом с левой
линией. Нет: чисто белый текст, второй акцентный цвет, mono в подписях,
серый как цвет основного текста.

## Видео

Шкала Full HD без сдвига: титул 120 px, заголовок 84 px Playfair Display 700,
подписи 38 px Spectral, пояснения 30 px, служебный 26 px JetBrains Mono.
Проявление 440 мс с подъёмом 12 px, подпись ждёт объекты 480 мс. Линии 5 px,
карточки `--bg-2` со скруглением 6 px, одно слово заголовка курсивом в цвете
акцента. Декор: тёплое свечение в углу титульника на 8 процентов, не больше.

Переменные для `:root` сцены, поверх блока токенов:

```css
:root {
  --t-title: 120px; --t-h: 84px; --t-copy: 38px; --t-note: 30px; --t-meta: 26px; --display-weight: 700;
  --fade: 440ms; --fade-rise: 12px; --caption-pause: 480ms; --stroke: 5px;
}
```

Акцент текстом на фоне: `--accent` даёт 6.1:1 на `--bg`, им можно писать слова заголовка и метки; `--accent-2` для плоскостей, обводок и состояний, не для текста на фоне.

Все три гарнитуры содержат кириллицу и латиницу; гарнитура без письма языка объяснения молча подменяется браузером, и проверка шрифтов это ловит.
