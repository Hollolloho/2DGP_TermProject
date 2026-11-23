"""퍼즐 패널의 논리 픽셀 배치. 입력과 렌더가 같은 영역을 사용한다."""
PUZZLE_TABS = (('maze','마우스 미로',(66,52,120,28)),
               ('connection','통로 연결',(196,52,120,28)))
CONNECTION_BOARD = (70,126,42)
CONNECTION_SHELF = (282,130,184,164)
CONNECTION_SLOTS = ((314,158),(406,154),(354,208),(314,264),(416,260))


def contains(rect, point):
    x,y,w,h = rect
    return point is not None and x <= point[0] < x+w and y <= point[1] < y+h


def tab_at(point):
    return next((key for key,_,rect in PUZZLE_TABS if contains(rect,point)),None)


def connection_cell(point):
    x,y,size = CONNECTION_BOARD
    if contains((x,y,size*4,size*4),point):
        return int((point[0]-x)//size),int((point[1]-y)//size)
    return None


def connection_center(cell):
    x,y,size = CONNECTION_BOARD
    return x+(cell[0]+.5)*size,y+(cell[1]+.5)*size


def connection_piece_at(puzzle, point):
    cell = connection_cell(point)
    if cell is not None:
        return puzzle.piece_at(cell)
    size = CONNECTION_BOARD[2]
    return next((index for index,(x,y) in enumerate(CONNECTION_SLOTS)
                 if puzzle.pieces[index].cell is None and puzzle.held != index
                 and contains((x-size/2,y-size/2,size,size),point)),None)
