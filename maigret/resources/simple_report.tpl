<html>
<head>
    <meta charset="utf-8" />
</head>
<meta name="viewport" content="width=device-width, initial-scale=1.0, shrink-to-fit=no" />
<title>{{ username }} — Maigret 搜尋報告</title>
<link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css" integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T" crossorigin="anonymous">
<style>
    .table td, .table th {
        padding: .4rem;
    }
    @media print {
        .pagebreak { page-break-before: always; }
    }
    .label-zh { font-weight: 600; }
    .label-en { color: #888; font-size: 0.85em; margin-left: 4px; }
</style>
<body>
{% set field_zh = {
    'fullname': '全名',
    'username': '使用者名稱',
    'name': '名稱',
    'email': '電子郵件',
    'bio': '個人簡介',
    'location': '地點',
    'website': '網站',
    'url': '網址',
    'channel_url': '頻道網址',
    'image': '頭像',
    'id': 'ID',
    'youtube_channel_id': 'YouTube 頻道 ID',
    'latest_activity_at': '最後活動時間',
    'created_at': '建立時間',
    'updated_at': '更新時間',
    'followers': '追蹤者數',
    'following': '追蹤中數',
    'is_family_safe': '兒少友善',
    'extractor': '資料來源',
    'verified': '已驗證',
    'country': '國家',
    'city': '城市',
    'gender': '性別',
    'age': '年齡',
    'posts': '貼文數',
    'likes': '按讚數',
    'views': '觀看數',
    'subscribers': '訂閱者數',
    'description': '描述',
    'nickname': '暱稱',
    'first_name': '名',
    'last_name': '姓',
    'phone': '電話',
    'twitter': 'Twitter',
    'github': 'GitHub',
    'instagram': 'Instagram'
} %}
    <div class="container">
        <div class="row-mb">
            <div class="col-12 card-body" style="padding-bottom: 0.5rem;">
                <h4 class="mb-0">
                    <a class="blog-header-logo text-dark" href="#">
                        <span class="label-zh">{{ username }} 的搜尋報告</span>
                        <span class="label-en">/ Username search report for {{ username }}</span>
                    </a>
                </h4>
                <small class="text-muted">由 <a href="https://github.com/soxoj/maigret">Maigret</a> 產生於 {{ generated_at }}</small>
            </div>
        </div>
        <div class="row-mb">
            <div class="col-md">
                <div class="card flex-md-row mb-4 box-shadow h-md-250">
                    <div class="card-body d-flex flex-column align-items-start">
                        <h5><span class="label-zh">推測個人資料</span> <span class="label-en">/ Supposed personal data</span></h5>
                        {% for k, v in supposed_data.items() %}
                        <span>
                            {{ k }}: {{ v }}
                        </span>
                        {% endfor %}
                        {% if countries_tuple_list %}
                        <span>
                            <span class="label-zh">地理位置</span><span class="label-en">(Geo)</span>：{% for k, v in countries_tuple_list %}{{ k }} <span class="text-muted">({{ v }})</span>{{ ", " if not loop.last }}{% endfor %}
                        </span>
                        {% endif %}{% if interests_tuple_list %}
                        <span>
                            <span class="label-zh">興趣標籤</span><span class="label-en">(Interests)</span>：{% for k, v in interests_tuple_list %}{{ k }} <span class="text-muted">({{ v }})</span>{{ ", " if not loop.last }}{% endfor %}
                        </span>
                        {% endif %}{% if first_seen %}
                        <span>
                            <span class="label-zh">首次出現</span><span class="label-en">(First seen)</span>：{{ first_seen }}
                        </span>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
        <div class="row-mb">
            <div class="col-md">
                <div class="card flex-md-row mb-4 box-shadow h-md-250">
                    <div class="card-body d-flex flex-column align-items-start">
                        <h5><span class="label-zh">摘要</span> <span class="label-en">/ Brief</span></h5>
                        <span>
                            {{ brief }}
                        </span>
                    </div>
                </div>
            </div>
        </div>
        {% for u, t, data in results %}
            {% for k, v in data.items() %}
                {% if v.found and not v.is_similar %}
        <div class="row-mb">
            <div class="col-md">
                <div class="card flex-md-row mb-4 box-shadow h-md-250">
                    <img class="card-img-right flex-auto d-md-block" alt="Photo" style="width: 200px; height: 200px; object-fit: scale-down;" src="{{ v.status and v.status.ids_data and v.status.ids_data.image or 'https://i.imgur.com/040fmbw.png' }}" data-holder-rendered="true">
                    <div class="card-body d-flex flex-column align-items-start" style="padding-top: 0;">
                    <h3 class="mb-0" style="padding-top: 1rem;">
                        <a class="text-dark" href="{{ v.url_main }}" target="_blank">{{ k }}</a>
                    </h3>
                    {% if v.status.tags %}
                        <div class="mb-1 text-muted"><span class="label-zh">標籤</span><span class="label-en">(Tags)</span>：{{ v.status.tags | join(', ') }}</div>
                    {% endif %}
                    <p class="card-text">
                        <a href="{{ v.url_user }}" target="_blank">{{ v.url_user }}</a>
                    </p>
                    {% if v.ids_data %}
                    <table class="table table-striped">
                        <tbody>
                        {% for k1, v1 in v.ids_data.items() %}
                            {% if k1 != 'image' %}
                            <tr>
                                <th>{% if k1 in field_zh %}<span>{{ field_zh[k1] }}</span> <span style="color:#888;font-size:0.82em;font-weight:400;">{{ title(k1) }}</span>{% else %}{{ title(k1) }}{% endif %}</th>
                                <td>{% if v1 is iterable and (v1 is not string and v1 is not mapping) %}{{ v1 | join(', ') }}{% else %}{{ detect_link(v1) }}{% endif %}
                                </td>
                            </tr>
                            {% endif %}
                        {% endfor %}
                        </tbody>
                    </table>
                    {% endif %}
                  </p>
                </div>
                </div>
            </div>
        </div>
                {% endif %}
            {% endfor %}
        {% endfor %}
    </div>
    <script src="https://code.jquery.com/jquery-3.3.1.slim.min.js" integrity="sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo" crossorigin="anonymous"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.14.7/umd/popper.min.js" integrity="sha384-UO2eT0CpHqdSJQ6hJty5KVphtPhzWj9WO1clHTMGa3JDZwrnQq4sF86dIHNDz0W1" crossorigin="anonymous"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/js/bootstrap.min.js" integrity="sha384-JjSmVgyd0p3pXB1rRibZUAYoIIy6OrQ6VrjIEaFf/nJGzIxFDsf4x0xIM+B07jRM" crossorigin="anonymous"></script>
</html>
