#!/bin/bash

URL="http://localhost:8080/getRemoteTask"
NUM_REQUESTS=75

for i in $(seq 1 $NUM_REQUESTS); do
    curl -X POST "$URL" \
         -H "Content-Type: application/json" \
         -d '{
               "imagen": "nicodigo/worker_hit1:1.0",
               "tarea": "ocurrencias_palabras",
               "parametros": {},
               "datos": {"cuerpo_texto": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aliquam eu egestas purus, non rutrum sem. Nullam ut ex sit amet leo varius rutrum. Etiam ultrices maximus mauris vitae varius. Phasellus consequat arcu vel nisi porttitor, sit amet rhoncus elit malesuada. Donec tincidunt, nibh ac tristique cursus, libero lectus mollis nulla, sit amet tempus erat lorem in nulla. Mauris eu blandit ex. Suspendisse sollicitudin fermentum massa vel fermentum. Phasellus suscipit volutpat justo, eget efficitur ex fermentum egestas. Quisque mattis turpis justo, vitae euismod massa fringilla id. Nunc a cursus tellus, ac vehicula erat. Orci varius natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus. Ut porta varius tellus nec pharetra. Fusce blandit mauris vel commodo consequat. Phasellus fermentum faucibus dignissim. Nulla facilisi. Maecenas ac massa tristique, fringilla lectus et, finibus sem. Pellentesque fermentum ac tortor id vulputate. Fusce at convallis erat. Proin leo risus, iaculis et scelerisque a, sagittis non est. Praesent finibus nibh vel magna varius, id tincidunt enim dignissim. Pellentesque blandit vitae justo at tincidunt. Vestibulum ac justo at dui aliquet imperdiet. Phasellus scelerisque, nisl vitae gravida varius, lacus tellus accumsan erat, sed luctus ex sapien at eros. Donec elit lorem, sagittis vitae lacus in, condimentum egestas mauris. Sed finibus orci eu aliquet pellentesque. Maecenas elit ex, dapibus et nisi et, volutpat porta leo. Donec nec massa at nisi hendrerit ullamcorper non sit amet nulla. Mauris non neque urna. In hac habitasse platea dictumst. Nam ultricies porttitor dolor, nec tempus ex suscipit a. Praesent sit amet leo efficitur, blandit ligula mollis, vehicula felis. Donec condimentum metus eu dolor varius egestas. Ut in felis nec ante pellentesque auctor quis quis leo. Ut at diam massa. Phasellus nisi nisl, efficitur in enim eget, interdum feugiat diam. Pellentesque habitant morbi tristique senectus et netus et malesuada fames ac turpis egestas. Cras fermentum venenatis quam. Aenean eu nisl vitae massa convallis mollis ut quis turpis. Duis posuere non mauris at viverra. Donec felis nunc, sollicitudin eget luctus in, mollis vel orci. Morbi tempus, neque vitae euismod tempor, dolor velit interdum tortor, nec cursus ex sem eget orci. Nullam mattis sit amet urna quis congue. Curabitur id semper magna. Integer feugiat libero elementum justo pretium, eget rutrum elit gravida. Praesent finibus posuere purus. Ut porta tempus quam, eget egestas metus pellentesque ut. Nulla at lacus lacus. Ut porttitor pellentesque erat a tristique. Nunc et iaculis augue, non ullamcorper turpis. In hac habitasse platea dictumst. "}
             }'\
    &
done
wait

echo "terminé"
