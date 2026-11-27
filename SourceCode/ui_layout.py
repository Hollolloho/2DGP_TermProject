"""고정 640×400 화면의 공용 fit과 SDL 창/렌더러 좌표 변환."""
LOGICAL_WIDTH, LOGICAL_HEIGHT = 640,400


def fit_viewport(width, height):
    # 8:5 정수 사각형으로 두 축의 배율을 같게 유지한다.
    unit = max(0,min(width//8,height//5))
    w,h = unit*8,unit*5
    return (width-w)//2,(height-h)//2,w,h


def window_to_logical(point, window_size, output_size):
    ww,wh = window_size
    ow,oh = output_size
    x,y,w,h = fit_viewport(ow,oh)
    if min(ww,wh,w,h) <= 0:return None
    rx,ry = point[0]*ow-x*ww,point[1]*oh-y*wh
    if not (0 <= rx < w*ww and 0 <= ry < h*wh):return None
    return int(rx*LOGICAL_WIDTH//(w*ww)),int(ry*LOGICAL_HEIGHT//(h*wh))


def logical_to_window(point, window_size, output_size):
    """논리 지점을 SDL 창 픽셀로 옮긴다. 축소/DPI 반올림도 표시 영역 안에 둔다."""
    ww,wh = window_size
    ow,oh = output_size
    x,y,w,h = fit_viewport(ow,oh)
    if min(ww,wh,w,h) <= 0:return None
    nx,ny = (x*LOGICAL_WIDTH+int(point[0])*w)*ww,(y*LOGICAL_HEIGHT+int(point[1])*h)*wh
    dx,dy = ow*LOGICAL_WIDTH,oh*LOGICAL_HEIGHT
    px,py = (nx+dx-1)//dx,(ny+dy-1)//dy
    if 0 <= point[0] < LOGICAL_WIDTH:
        px = min(px,((x+w)*ww+ow-1)//ow-1)
    if 0 <= point[1] < LOGICAL_HEIGHT:
        py = min(py,((y+h)*wh+oh-1)//oh-1)
    return px,py
