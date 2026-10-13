# Kết quả bước 1 — semantic review 39 ca verifier

Ngày review: **2026-10-13**. Reviewer: **Codex (AI semantic reviewer)**.
Nguồn: output `logic_v3` trong ZIP `rag-validation-20261012T165922Z.zip`.

**Đã hoàn thành review bằng AI đủ 39 ca. Đánh giá độc lập bằng người vẫn chờ.**
Phạm vi lần này kết thúc tại bước 1; bước 2–4 chờ người dùng quyết định.

## 1. Kết quả

| Hạng mục | Kết quả |
| --- | ---: |
| Ca đã đọc claim, context và output | 39/39 |
| Giá trị chấm theo năm tiêu chí | 195 |
| Nhãn đúng theo diễn giải bộ ca hiện tại | 37/39 |
| Ca đạt toàn bộ tiêu chí áp dụng | 29/39 |
| Ca có ít nhất một lỗi output | 10/39 |
| Ca kết luận support sai | 2/39 |
| Ca có cách diễn đạt dữ liệu cần làm rõ | 2/39 |

Trong 10 output cần sửa, hai ca sai nhãn và tám ca đúng nhãn nhưng có lỗi về
trích dẫn, giải thích, phạm vi kiểm chứng hoặc thông tin thiếu. Các nhóm này
không cộng thêm vào nhau. Hai vấn đề diễn đạt dữ liệu được ghi riêng ở mục 4.

Gate tự động của lượt model vẫn **không đạt**. Review này không đổi nhãn gold,
prediction, tiêu chí đánh giá hoặc kết quả inference đã lưu; không đưa candidate
vào runtime đang phục vụ. Không chạy model hoặc notebook mới trong bước này.

## 2. Cách chấm

| Tiêu chí | Đạt / số ca áp dụng | Không áp dụng |
| --- | ---: | ---: |
| Nhãn đúng (`label_correct`) | 37/39 | 0 |
| Trích dẫn liên quan (`quote_relevant`) | 31/33 | 6 |
| Giải thích suy ra được từ bằng chứng (`explanation_follows_evidence`) | 32/39 | 0 |
| Đủ thành phần cần kiểm chứng (`all_claim_parts_checked`) | 33/39 | 0 |
| Thông tin thiếu cụ thể và đúng (`missing_information_specific`) | 11/13 | 26 |

- Nhãn được đối chiếu với toàn context. `not_enough_info` (NEI) nghĩa là chưa
  đủ thông tin để xác nhận hoặc bác bỏ claim.
- Quote phải nguyên văn và liên quan đến quyết định. Quote có liên quan vẫn
  có thể thiếu bằng chứng cho một vế khác; tiêu chí độ phủ kiểm riêng việc đó.
- `support` phải chứng minh đủ các vế. Bác bỏ một claim nối bằng AND chỉ cần
  một vế bị phản bác rõ trong đúng phạm vi. Với “một số”, muốn bác bỏ phải
  có bằng chứng không tồn tại trường hợp thỏa mãn trong toàn tập được nói đến.
- Đại từ như “these four” có thể được giải nghĩa từ câu liền trước trong
  context; không bắt buộc quote lặp lại mọi tiền ngữ.
- Quote rỗng hợp lệ ở ca NEI được ghi N/A. Thông tin thiếu rỗng khi claim đã
  đủ dữ liệu quyết định cũng là N/A. JSONL giữ `true` cho các mục N/A để tương
  thích cấu trúc cũ, đồng thời ghi `rubric_applicability=false`; chúng được
  loại khỏi mẫu số tương ứng trong bảng trên.
- Đây là review mô tả sau khi đã xem output. Các tỷ lệ này không phải kết quả
  đánh giá độc lập hoặc tiêu chí mới được đóng băng trước inference.

## 3. Mười output cần sửa

Các yêu cầu sửa dưới đây là kết luận review; chưa thực hiện thay đổi model/code.

| Case ID | Vấn đề đã quan sát | Yêu cầu đối với output đúng |
| --- | --- | --- |
| `contract:partial_accuracy` | Chỉ có bằng chứng giảm memory nhưng model xác nhận cả accuracy 94%; sai nhãn. | NEI; giữ phần memory đã biết và chỉ rõ thiếu accuracy. |
| `contract:both_supported` | Nhãn và quote đúng, nhưng explanation nói claim chỉ tập trung memory, loại accuracy khỏi phạm vi kiểm. | Giải thích bằng chứng cho cả memory và accuracy. |
| `contract:irrelevant` | Nhãn NEI đúng; missing information tự thêm điều kiện “on a Tuesday”. | Chỉ yêu cầu accuracy liên quan claim, không thêm điều kiện ngoài claim. |
| `contract:cross_sentence` | Nhãn đúng; quote/reasoning chỉ chứng minh bốn model, bỏ qua hai dataset. | Dẫn và giải thích cả số model lẫn số dataset. |
| `scope:existential:contradict` | Nhãn đúng nhưng chỉ dùng hai node chậm hơn để bác bỏ “một số”; bỏ node còn lại. | Kiểm đủ tập Birch/Elm/Fir và giải thích không node nào giảm thời gian phản hồi. |
| `scope:direction:contradict` | 42 ms → 55 ms bị kết luận là giảm; sai nhãn. | Nhận diện tăng 13 ms và bác bỏ claim giảm; không có dữ liệu còn thiếu. |
| `scope:metric:not_enough_info` | Nhãn NEI đúng nhưng explanation gọi recall 0.64 → 0.79 là precision. | Giữ đúng tên metric; nêu precision chưa được đo. |
| `scope:conjunction:support` | Context đủ hai vế; quote và explanation chỉ chứng minh giảm memory, thiếu tăng recall. | Chứng minh từng vế trước khi xác nhận toàn claim. |
| `scope:conjunction:contradict` | Explanation dùng recall giảm để bác bỏ đúng, nhưng quote chỉ nói memory giảm. | Quote phải chứa phản chứng về recall. |
| `scope:condition:not_enough_info` | Theo diễn giải của bộ ca, NEI đúng nhưng quote chỉ nói nhóm nhiệt độ cao. | Dẫn đúng phần thiếu phép đo ở nhóm nhiệt độ thấp; làm rõ câu dữ liệu như mục 4. |

Hai false support là `contract:partial_accuracy` và
`scope:direction:contradict`. Những lỗi khác cho thấy chỉ nhìn accuracy sẽ bỏ
sót chất lượng lập luận và bằng chứng mà Writer có thể sử dụng về sau.

## 4. Hai điểm diễn đạt dữ liệu cần làm rõ

1. **`scope:existential:support`:** context nói “Birch became faster”, còn
   claim nói giảm thời gian phản hồi. Review giữ `support` theo cách hiểu của
   bộ ca rằng “faster” là giảm thời gian phản hồi; từ này đứng riêng có thể
   chỉ một khía cạnh hiệu năng khác. Một phiên bản dữ liệu tương lai nên nêu
   trực tiếp metric để người đánh giá độc lập không phải suy đoán.
2. **`scope:condition:not_enough_info`:** “no yield changes were measured”
   có thể được hiểu là chưa đo thay đổi, hoặc đã đo và thấy không thay đổi.
   Review giữ NEI theo ý định “chưa đo” của bộ ca. Cần diễn đạt rõ nếu tạo
   phiên bản dữ liệu mới; không sửa gold hoặc tính lại lượt hiện tại để đạt gate.

Vì vậy, các số **37/39** và **29/39** ở đây đi kèm diễn giải bộ ca hiện tại.
Người review độc lập cần xác nhận hoặc phân xử hai điểm trên. Bộ 39 ca đã
được xem trong quá trình phát triển, không còn là bộ kiểm thử giữ kín độc lập.

## 5. Hồ sơ bàn giao

- [Phiếu đủ 39 ca, từng judgment và nhận xét](VERIFIER_SEMANTIC_REVIEW_20261012T165922Z.md).
- [39 bản ghi review có cấu trúc](blind-verifier-review-draft-20261012T165922Z.jsonl).
- [Tổng hợp số liệu, rubric và hash nguồn](blind-verifier-semantic-review-20261012T165922Z.json).
- [Đối chiếu ZIP và kết quả inference trước review](BLIND_VERIFIER_REVIEW_20261012T165922Z.md).
- [Kiểm tra tính toàn vẹn hồ sơ review](step1-semantic-review-validation.json).

Đã kiểm tra: 39 ID duy nhất, 195 judgments, số liệu tổng hợp khớp từng dòng,
39 mục trong phiếu, trích dẫn nằm trong context, các trường dữ liệu/model gốc
khớp nguồn, hash của 37 output files và hash/CRC ZIP khớp. Đây là kiểm tra
tính toàn vẹn hồ sơ; không thay thế review ngữ nghĩa độc lập bằng người.

Trạng thái: **bước 1 hoàn thành phần review bằng AI; đánh giá độc lập bằng
người còn chờ. Bước 2–4 chưa thực hiện trong lượt này, chờ quyết định của
người dùng.** Atomic verifier chưa được triển khai. Không có thay đổi runtime
hoặc xác nhận hoàn thành toàn dự án từ kết quả review này.
